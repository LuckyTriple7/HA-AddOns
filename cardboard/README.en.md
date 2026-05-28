# CardBoard

Home Assistant Add-on – displays HA sensor data as Markdown cards in the browser.

## Features

- Jinja2 templates rendered directly via the HA API
- Multiple users with individual views (read-only)
- 1–3 cards side by side (automatically determined by template count)
- Markdown rendering (headings, bold, tables, …)
- Whitespace alignment preserved (monospace font)
- Cookie session (7 days)
- Configurable refresh interval
- Responsive layout

## Quick Start

1. Install and start the add-on
2. Enter your HA Long-Lived Access Token in the options
3. Create `/config/addons_config/cardboard/users.yaml`
4. Place template files under `/config/addons_config/cardboard/<username>/`
5. Open the web interface at `http://<HA-IP>:17772`

Full documentation: see **DOCS.en.md**
