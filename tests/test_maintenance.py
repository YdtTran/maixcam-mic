"""Recording exclusion, ownership, restart persistence and real HTTP contract."""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock

from pc.multistream_recording import MultistreamRecording
from pc.operator_server import RecordingManager, make_handler


OWNER = "a" * 32
FOREIGN = "b" * 32


class MaintenanceTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows script and real operator integration")
    def test_windows_guard_blocks_real_record_request_after_preflight(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(Path(directory) / 'recordings', spawn=Mock())
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            script = Path(directory) / 'test.ps1'
            script.write_text(r'''
$ErrorActionPreference='Stop'
$module = Import-Module '__MODULE__' -PassThru -DisableNameChecking
& $module {
    function script:Get-MaintenanceOperator { return 'running' }
    function script:Invoke-MaintenanceDocker {
        param([string[]]$Arguments)
        $code = $Arguments[-1].Replace('127.0.0.1:8000', '127.0.0.1:__PORT__')
        $result = & '__PYTHON__' -c $code
        if ($LASTEXITCODE -ne 0) { throw 'Operator request refused' }
        return $result
    }
}
[void](Invoke-MaintenanceApi '__ROOT__')
$guard = Enter-ProjectMaintenance '__ROOT__'
try {
    try {
        Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:__PORT__/api/recordings/start' -Method Post
        throw 'Recording started during mutation'
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 409) { throw }
    }
    $nested = Enter-ProjectMaintenance '__ROOT__'
    Exit-ProjectMaintenance $nested $true
    $status = Invoke-MaintenanceApi '__ROOT__'
    if ($status.maintenance.owner -cne $guard.Owner -or $status.recording) { throw 'Mutation guard lost' }
} finally { Exit-ProjectMaintenance $guard $true }
'''.replace('__MODULE__', str(Path(__file__).resolve().parents[1] / 'scripts/NetworkDeployment.psm1'))
                .replace('__PORT__', str(server.server_port)).replace('__ROOT__', directory)
                .replace('__PYTHON__', sys.executable))
            try:
                result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(script)],
                                        capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIsNone(manager.maintenance())
                manager.spawn.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)

    def test_owner_persistence_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(directory, spawn=Mock())
            self.assertIsNone(manager.status()["maintenance"])
            self.assertEqual(manager.begin_maintenance(OWNER)["maintenance"], {"owner": OWNER})
            manager.begin_maintenance(OWNER)
            restored = RecordingManager(directory, spawn=Mock())
            for instance in (manager, restored):
                with self.assertRaisesRegex(RuntimeError, "Maintenance is active"):
                    instance.start()
                with self.assertRaisesRegex(RuntimeError, "another owner"):
                    instance.begin_maintenance(FOREIGN)
                with self.assertRaisesRegex(RuntimeError, "another owner"):
                    instance.end_maintenance(FOREIGN)
                instance.spawn.assert_not_called()
                self.assertEqual(instance.list_recordings(), [])
            restored.end_maintenance(OWNER)
            self.assertIsNone(manager.status()["maintenance"])
            manager.end_maintenance(OWNER)

    def test_capture_and_finalization_refuse_acquisition(self):
        with tempfile.TemporaryDirectory() as directory:
            for finalizing in (False, True):
                manager = RecordingManager(directory)
                process = Mock(spec=MultistreamRecording)
                process.poll.return_value = None
                process.status.return_value = {"finalizing": finalizing}
                manager._process = process
                with self.assertRaisesRegex(RuntimeError, "wait for finalization"):
                    manager.begin_maintenance(OWNER)
                self.assertFalse((Path(directory) / ".maintenance.json").exists())

    def test_invalid_marker_and_invalid_owners_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(directory)
            for owner in (None, True, "", "A" * 32, "../file", "a" * 33):
                with self.assertRaises(ValueError):
                    manager.begin_maintenance(owner)
                with self.assertRaises(ValueError):
                    manager.end_maintenance(owner)
            marker = Path(directory) / ".maintenance.json"
            for contents in ("{", "[]", "null", '{}', '{"owner": true}', '\ufffd'):
                marker.write_text(contents, encoding="utf-8")
                self.assertIn("error", manager.status()["maintenance"])
                with self.assertRaises(RuntimeError):
                    manager.start()
                with self.assertRaises(RuntimeError):
                    manager.end_maintenance(OWNER)
                self.assertEqual(marker.read_text(encoding="utf-8"), contents)

    def test_record_start_and_maintenance_acquisition_have_one_winner(self):
        for _ in range(12):
            with tempfile.TemporaryDirectory() as directory:
                process = Mock()
                process.poll.return_value = None
                manager = RecordingManager(directory, recording_mode="legacy", spawn=Mock(return_value=process))
                barrier = threading.Barrier(2)
                results = []

                def attempt(name, operation):
                    barrier.wait(timeout=3)
                    try:
                        operation()
                        results.append(name)
                    except RuntimeError:
                        pass

                threads = [threading.Thread(target=attempt, args=("record", manager.start)),
                           threading.Thread(target=attempt, args=("maintenance", lambda: manager.begin_maintenance(OWNER)))]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(5)
                    self.assertFalse(thread.is_alive())
                self.assertEqual(len(results), 1)
                if results == ["record"]:
                    self.assertIsNone(manager.maintenance())
                    manager.stop()
                else:
                    manager.spawn.assert_not_called()

    def test_real_http_owner_contract_and_record_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            manager = RecordingManager(directory, spawn=Mock())
            server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(manager))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"

            def post(path, body):
                request = urllib.request.Request(base + path, data=json.dumps(body).encode())
                try:
                    with urllib.request.urlopen(request, timeout=3) as response:
                        return response.status, json.load(response)
                except urllib.error.HTTPError as error:
                    return error.code, json.load(error)

            try:
                self.assertEqual(post('/api/maintenance/begin', [OWNER])[0], 400)
                self.assertEqual(post('/api/maintenance/begin', {"owner": OWNER})[0], 200)
                self.assertEqual(post('/api/maintenance/end', {"owner": FOREIGN})[0], 409)
                for _ in range(3):
                    request = urllib.request.Request(base + '/api/recordings/start', data=b'')
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(request, timeout=3)
                    self.assertEqual(error.exception.code, 409)
                self.assertEqual(post('/api/maintenance/end', {"owner": OWNER})[0], 200)
                manager.spawn.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)
