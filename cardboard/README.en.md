# CardBoard

Home Assistant Add-on – displays HA sensor data as Markdown cards in the browser.

## Features

- Jinja2 templates rendered directly via the HA API
- Multiple users with individual views
- Configurable card layout (1–`max_cards` cards side by side)
- Markdown rendering (headings, bold, tables, …)
- **Admin Panel** – user management and template editor directly in the browser
- Template editor with live preview
- Dark / Light mode
- Switchable language (🇩🇪 / 🇬🇧)
- Rate limiting – IP block after too many failed attempts
- PWA-ready – installable as an app on iOS/Android
- Cookie session (configurable, default: 7 days)
- Configurable refresh interval
- Responsive layout (mobile: cards stacked vertically)

## Quick Start

1. Install and start the add-on
2. Enter your HA Long-Lived Access Token in the options
3. Open the web interface at `http://<HA-IP>:17772`
4. Open the Admin Panel at `http://<HA-IP>:17773/admin/`
5. Create your first user and set up templates

Full documentation: see **DOCS.en.md**
