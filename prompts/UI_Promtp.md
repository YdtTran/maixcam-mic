Build a fast prototype web application called "WorkerCam Admin".

The purpose of this prototype is to visually demonstrate a worker body-camera monitoring dashboard for MaixCAM devices.

This is NOT a production implementation.

The most important goals are:

1. The UI must look polished and close to the provided reference screenshot.

2. The main interactions must appear functional.

3. The implementation must stay very small and fast.

4. Any difficult backend/media/device functionality may be mocked.

5. Do not overengineer anything.

Use:

Frontend:

- React

- TypeScript

- Vite

- Lucide React icons

- simple CSS or Tailwind if already convenient

Backend:

- FastAPI

- minimal Python code

- mock/demo data

Deployment:

- Docker Compose

The prototype should be runnable with:

docker compose up -d

==================================================

GENERAL VISUAL STYLE

==================================================

The interface should look like a real industrial monitoring/admin dashboard.

It should NOT look like:

- a startup landing page

- a futuristic AI dashboard

- a mobile app

- a gaming interface

- a highly decorative SaaS dashboard

The visual style should be restrained, functional, and enterprise-like.

Use:

- very light gray overall page background

- white cards and panels

- dark navy text

- muted gray secondary text

- blue as the main action color

- green only for healthy/online states

- red only for live/recording states

- thin light-gray borders

- very subtle shadows

- small-to-medium border radius

- compact spacing

- no gradients

- no glassmorphism

- no neon colors

- no oversized rounded cards

Target layout:

1920×1080 desktop.

The application should fill the browser viewport.

The dashboard should visually resemble CCTV/control-room software, but modern and clean.

==================================================

PAGE STRUCTURE

==================================================

The dashboard has four major areas:

1. Top navigation bar

2. Left sidebar

3. Main live video area

4. Right device information panel

Think of the screen as:

┌─────────────────────────────────────────────────────────────────────┐

│ WorkerCam Admin        Search workers, devices...       Admin ▾     │

├───────────────┬──────────────────────────────────┬──────────────────┤

│               │                                  │                  │

│ Live Workers  │ Worker #07 — Nguyen A      LIVE │ Device Status    │

│ Recordings    │                                  │                  │

│ Settings      │                                  │ Device   Online │

│               │                                  │ Recording On    │

│               │           LIVE VIDEO             │ Headset Connected│

│               │                                  │ Battery    78%  │

│               │                                  │ Signal     Good │

│               │                                  │ Microphone On   │

│               │                                  │                  │

│               │                                  │ Actions         │

│               │                                  │ [ Talk ][Record]│

└───────────────┴──────────────────────────────────┴──────────────────┘

The center live video should dominate the screen.

The right panel should be clearly narrower than the video area.

The left sidebar should be compact.

==================================================

TOP NAVIGATION BAR

==================================================

Create a full-width top navigation bar around 64px high.

Background:

white.

Bottom:

thin light gray divider.

LEFT SIDE

Show the application name:

WorkerCam Admin

Styling:

- dark navy

- bold or semi-bold

- around 20–22px

- vertically centered

- approximately 28px left padding

Do not add a logo icon unless extremely simple.

CENTER

Place a large search input.

Placeholder:

Search workers, devices...

Appearance:

- approximately 600–750px wide on a 1920px screen

- height around 40–44px

- pale gray-blue background

- no strong border

- small search icon on the left

- subtle rounded corners around 6–8px

- muted placeholder text

The search field does not need advanced functionality.

RIGHT SIDE

Show:

- notification bell icon

- small red notification dot

- circular avatar

- initials "AD"

- text "Admin"

- downward chevron

Keep everything horizontally aligned.

Do not add menus unless trivial.

==================================================

LEFT SIDEBAR

==================================================

The sidebar begins directly underneath the top bar.

Width:

approximately 230–260px.

Background:

white or slightly off-white.

Right edge:

thin gray border.

Menu items:

Live Workers

Recordings

Settings

Each item should be approximately 52–58px tall.

Each has:

- icon on the left

- text on the right

- comfortable horizontal padding

Use Lucide icons such as:

Live Workers:

Users or UserRound

Recordings:

SquarePlay, Video, or FileVideo

Settings:

Settings

ACTIVE MENU ITEM

"Live Workers" should initially be active.

Active appearance:

- very pale blue background

- blue icon

- blue text

- narrow vertical blue bar at the far left

- no strong shadow

Inactive items:

- dark gray / blue-gray text

- gray icons

- transparent background

Hover:

very subtle light-gray background.

Do NOT add:

Overview

Dashboard Home

Worker Management

Tasks

Alerts

Reports

AI Detection

Analytics

Recent Activity

==================================================

MAIN CONTENT AREA

==================================================

The main content sits between the sidebar and the right status area.

Give it around 24–32px padding from the edges.

The main video card should occupy most of the available width.

The content should feel spacious but not empty.

Do not fill the page with additional cards.

==================================================

LIVE VIDEO CARD

==================================================

This is the most important visual element.

Create one large rectangular card.

Width:

fill almost all available center-column width.

Height:

large enough that the camera feed visually dominates the dashboard.

Aspect ratio:

roughly 16:9 or slightly taller.

Card styling:

- white background

- small border radius around 8px

- overflow hidden

- thin subtle border

- no large shadow

------------------------------------------

VIDEO HEADER

------------------------------------------

Add a dark header bar directly above the camera feed.

Height:

approximately 68–76px.

Background:

very dark navy/charcoal.

Example:

#16212E

LEFT SIDE

Show:

green circular dot

then:

Worker #07 — Nguyen A

Text:

white

medium/semibold

around 18–20px

The green dot should be about 14–16px.

RIGHT SIDE

Show a bright red LIVE badge.

Example:

● LIVE

The badge should:

- have solid red background

- white text

- small rounded corners

- compact size

- appear clearly visible

Next to it show:

08:16:24

in muted light-gray text.

This can be a running local/demo timer.

------------------------------------------

VIDEO BODY

------------------------------------------

Use a demo video showing an industrial environment, preferably first-person worker perspective.

The video should fill the card.

Use:

object-fit: cover

No letterboxing if avoidable.

The video itself should visually take up roughly 65–75% of the main dashboard height.

Do not put large controls over the video.

BOTTOM-RIGHT CORNER

Place a small dark translucent rectangular control area containing only:

fullscreen icon

Keep it subtle.

Do not add:

- screenshot button

- seek bar

- previous worker button

- next worker button

- AI bounding boxes

- warning overlays

- maps

- compass

- accelerometer

- IMU

- worker task information

- GPS

- charts

- analytics

The live video must remain visually clean.

==================================================

WORKER SELECTION

==================================================

The prototype should contain exactly two demo workers.

Example:

Worker #07 — Nguyen A

Worker #12 — Tran B

Keep worker switching very simple.

Preferred implementation:

When the user clicks "Live Workers", show a compact worker selector near the top of the content area or as a simple dropdown above the video.

Possible design:

[ Worker #07 — Nguyen A ▾ ]

When expanded:

● Worker #07 — Nguyen A

● Worker #12 — Tran B

Online workers have a small green dot.

Selecting another worker updates:

- worker name

- status

- battery

- recording state

- video/demo stream

Do not build a complex worker table.

==================================================

RIGHT COLUMN

==================================================

The right side of the dashboard should be approximately 350–400px wide.

It contains two stacked cards:

1. Device Status

2. Actions

Leave around 20–24px spacing between them.

==================================================

DEVICE STATUS CARD

==================================================

Create a white card.

Header:

Device Status

Header styling:

- around 18–20px

- dark navy

- semibold

- padding around 20px

- bottom divider

Inside, show exactly six rows.

Rows:

Device

Recording

Headset

Battery

Signal

Microphone

Each row should be around 64–72px tall.

Use thin horizontal separators.

Each row has three conceptual areas:

LEFT:

status icon

CENTER:

label

RIGHT:

status value

Example:

●    Device        Online

●    Recording     On

🎧   Headset       Connected

🔋   Battery       78%

▂▅▇ Signal        Good

🎙   Microphone    On

Use actual Lucide icons rather than emoji.

------------------------------------------

DEVICE ROW

------------------------------------------

Icon:

solid green circle

Label:

Device

Right value:

Online

Value color:

green

------------------------------------------

RECORDING ROW

------------------------------------------

Icon:

solid red circle when recording

Label:

Recording

Value:

On

Value color:

green or dark text.

If recording is off:

gray circle

Off

------------------------------------------

HEADSET ROW

------------------------------------------

Use headphones icon.

Label:

Headset

Value:

Connected

Value:

green text.

Disconnected:

gray/red as appropriate.

------------------------------------------

BATTERY ROW

------------------------------------------

Use BatteryMedium / BatteryFull icon.

Show a simple green fill indicator if convenient.

Label:

Battery

Value:

78%

Value should remain dark navy.

Do not turn battery percentage green unless desired.

------------------------------------------

SIGNAL ROW

------------------------------------------

Use a signal-bars icon.

Label:

Signal

Value:

Good

Bars:

green.

Value:

dark navy.

Possible values:

Good

Fair

Weak

------------------------------------------

MICROPHONE ROW

------------------------------------------

Use microphone icon.

Label:

Microphone

Value:

On

When enabled:

green value.

When disabled:

gray value.

==================================================

ACTIONS CARD

==================================================

Create another white card immediately below Device Status.

Header:

Actions

Use the same card header style.

Inside:

two equally sized buttons next to each other.

Layout:

[ 🎙 Talk ]    [ ● Record ]

Buttons should be around 52–60px high.

------------------------------------------

TALK BUTTON

------------------------------------------

Talk is the main action.

Appearance:

solid blue background

white text

white microphone icon

Use:

#1769E8 or similar.

Border radius:

6–8px.

Behavior:

When clicked or held:

change text to:

Talking...

Optionally make the button slightly darker.

Do not add animations beyond a simple state change.

If browser microphone permission is easy to implement, request it.

Otherwise mock it.

The visual interaction matters more than the real audio pipeline.

------------------------------------------

RECORD BUTTON

------------------------------------------

When not recording:

white background

gray border

red circular record icon

dark text

Label:

Record

When clicked:

change selected worker's recording state to true.

Button becomes:

Stop Recording

Possible appearance:

very pale red background

red border

red text

The Device Status "Recording" row should immediately change.

Clicking again stops the recording.

Create a fake recording entry for the Recordings page.

==================================================

RECORDINGS PAGE

==================================================

When the user clicks Recordings in the sidebar:

Keep the top navigation and sidebar identical.

Replace the center/right dashboard content with a recordings page.

Top of page:

Recordings

Use:

24px-ish bold dark navy text.

Optional small subtitle:

Saved worker camera recordings

Below this create ONE white table card.

Do not add filters unless trivial.

Table columns:

Worker

Start Time

Duration

Filename

Action

Example data:

Nguyen A

08:02:14

04:31

cam-007_2026-10-07_080214.mp4

Play   Download

Tran B

07:45:02

02:18

cam-012_2026-10-07_074502.mp4

Play   Download

Table styling:

- white background

- subtle outer border

- very light table header background

- thin row separators

- text around 14px

- header text medium weight

- generous row height around 56px

ACTION BUTTONS

Play:

small blue text/button

Download:

small neutral button/text

Clicking Play may open a simple modal.

Modal:

white panel centered over dark translucent backdrop.

Inside:

recording filename

HTML5 video player

Close button

Do not spend time building advanced playback controls.

==================================================

SETTINGS PAGE

==================================================

Keep this page intentionally minimal.

Title:

Settings

Show one white card.

Card title:

Prototype Settings

Inside show simple rows:

Demo Mode        Enabled

Backend          WorkerCam Backend

Environment      Prototype

Optional:

[ Logout ]

Do not build configuration editors.

==================================================

LOGIN SCREEN

==================================================

When unauthenticated, show a standalone login screen.

Background:

same light gray as dashboard.

Place a white card approximately:

400–440px wide

centered horizontally

slightly above vertical center.

Card appearance:

- white

- thin border

- small shadow

- radius around 8px

- padding around 32px

Top:

WorkerCam Admin

Subtitle:

Admin Login

Fields:

Username

[ admin ]

Password

[ password ]

Button:

Sign In

Button should be full width and blue.

Default demo credentials:

admin

admin

Do not add:

Forgot password

Create account

Google login

Remember me

MFA

Terms and Conditions

Keep it clean.

==================================================

DEMO DATA

==================================================

Use two workers.

Worker 1:

{

  id: "cam-007",

  device_name: "MaixCAM 07",

  worker_name: "Nguyen A",

  online: true,

  headset_connected: true,

  battery: 78,

  signal: "Good",

  microphone_on: true,

  recording: true

}

Worker 2:

{

  id: "cam-012",

  device_name: "MaixCAM 12",

  worker_name: "Tran B",

  online: true,

  headset_connected: true,

  battery: 64,

  signal: "Fair",

  microphone_on: true,

  recording: false

}

The values may slowly change.

For example:

every 30–60 seconds:

battery may decrease by 1.

Do NOT randomize every second.

The UI should remain stable during a demo.

==================================================

INTERACTION EXPECTATIONS

==================================================

All visible buttons should feel functional.

Required working interactions:

- login

- logout

- sidebar navigation

- switch worker

- Talk button active/inactive state

- Record start

- Record stop

- recording status update

- fake recording appears in Recordings

- Play recording/demo video

- fullscreen video button

Everything else can be static.

==================================================

RESPONSIVENESS

==================================================

Optimize primarily for:

1920×1080

Also make it usable around:

1366×768

At narrower desktop widths:

- sidebar may become slightly narrower

- right panel may shrink

- video should remain the largest element

Do not spend time creating a mobile navigation drawer.

For very narrow screens, simple overflow is acceptable for this prototype.

==================================================

BACKEND IMPLEMENTATION

==================================================

Keep the backend deliberately small.

Use FastAPI.

Create only enough APIs to make the frontend structure realistic.

Endpoints:

POST /api/auth/login

POST /api/auth/logout

GET /api/auth/me

GET /api/devices

GET /api/devices/{id}

POST /api/devices/{id}/record/start

POST /api/devices/{id}/record/stop

POST /api/devices/{id}/talk/start

POST /api/devices/{id}/talk/stop

GET /api/recordings

GET /api/health

DEMO_MODE=true by default.

In demo mode:

- use in-memory Python objects

- no real MaixCAM required

- no real UDP required

- no real Bluetooth required

- no real SSH required

- no PostgreSQL required unless trivial

- no migrations required

- no Redis

- no Kafka

- no MinIO

Talk endpoint:

simply log something like:

Talkback started for cam-007

Talkback stopped for cam-007

Record endpoint:

toggle demo recording state.

When recording stops:

create a fake recording record.

==================================================

FUTURE DEVICE INTERFACE

==================================================

Even though real device functionality is not required now, keep one small interface so it can be added later.

Example:

class DeviceGateway:

    async def start\_recording(device\_id): ...

    async def stop\_recording(device\_id): ...

    async def start\_talkback(device\_id): ...

    async def stop\_talkback(device\_id): ...

    async def get\_status(device\_id): ...

For demo mode implement:

DemoDeviceGateway

Do not implement the full production gateway yet.

Add comments indicating future real protocols:

MaixCAM media:

MPEG-TS over UDP

Talkback:

UDP port 9002

Bluetooth control:

HTTP port 8765

RTSP:

TCP port 8554

SSH:

port 22

But do not spend time implementing them for the prototype.

==================================================

DOCKER

==================================================

Keep Docker setup simple.

Structure:

workercam/

├── docker-compose.yml

├── [README.md](http://README.md)

├── frontend/

│   ├── Dockerfile

│   └── src/

└── backend/

    ├── Dockerfile

    ├── requirements.txt

    └── app/

docker compose should start:

frontend

backend

If an nginx server is convenient for serving the built frontend, use it.

Otherwise use the Vite server for the prototype.

Do not add unnecessary services.

==================================================

IMPLEMENTATION PRIORITY

==================================================

Spend effort in this order:

1. Dashboard visual accuracy

2. Large live video layout

3. Device status card

4. Talk / Record buttons

5. Login

6. Sidebar navigation

7. Worker switching

8. Recordings page

9. Demo backend

10. Docker

Do not spend significant effort on anything else.

If real implementation would slow the prototype down, mock it.

==================================================

IMPORTANT DESIGN RULE

==================================================

The final screen should visually resemble the supplied reference screenshot.

A user opening the application should immediately see:

- WorkerCam Admin header

- left navigation

- one very large worker camera feed

- worker name in a dark video header

- obvious red LIVE indicator

- compact device status panel on the right

- blue Talk button

- Record button

The video should visually receive the most attention.

The Device Status panel should receive the second most attention.

Everything else should remain visually quiet.

Do not introduce extra widgets just to fill space.

The prototype should feel intentional, simple, and believable.