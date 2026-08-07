# MyPage — Homepage Builder

Run your own homepage straight from Home Assistant — no design skills required. From a developer portfolio to a club page or a service provider's business card.

> 🇩🇪 Deutsche Version: [README.md](README.md)

## Features

- 🏠 **Public homepage** on port 17760 — profile, content sections, social links
- 🛠 **Admin panel** on port 17761 (login + brute-force protection) and via HA ingress in the sidebar
- 🧩 **Many content sections**: projects, blog, services, testimonials, team, photo albums, skills, timeline, news, **countdown**, events, link collection, FAQ, location & opening hours
- 📚 **Library**: a collection of standalone Markdown documents with freely chosen categories (travel guides, recipes, manuals …) at `/bibliothek` — each entry optionally with a **PDF**, either uploaded or generated from the text; the collection name is freely configurable
- 📄 **Custom pages**: standalone subpages (e.g. “About”, “Directions”) in Markdown (DE/EN) with their own address `/seite/<slug>`, optional nav entry and draft status
- 🧾 **Form builder**: freely configurable forms (sign-up, survey, request) with arbitrary fields; submissions in the messages tab + notification (email/Telegram/HA), honeypot + captcha
- ↪️ **Redirects (301/302)** + **Search Console verification** (Google/Bing) in the admin
- 🔒 **Members-only content**: blog posts, custom pages, photo albums or entire homepage sections restricted to logged-in members (guests see a teaser/lock + login prompt)
- 🔀 **Free ordering & visibility**: reorder sections by drag & drop and hide/show them individually (header stays on top, contact stays at the bottom)
- 🐙 **GitHub import**: enter a username, pick repos, done — description, stars, language and topics are imported, stars refreshed hourly
- 📅 **Appointment / booking button** (e.g. Calendly) — see [below](#-booking-calendar--appointment-button)
- ❤️ **Support button** (Buy Me a Coffee, Ko-fi, PayPal, Patreon, GitHub Sponsors …) with an automatic icon
- 🎨 **Design**: accent color, light/dark, layout, font (incl. custom font upload), custom CSS — plus **design templates** (one-click styles like “Elegant Dark”, “Light & Clean”, “Playful”)
- 🌍 **Bilingual** (DE/EN) with optional auto-translation; visitors can switch
- 👁 **Visitor counter & stats**: views, unique visitors, countries, browsers, referrers
- 📷 **Photo albums** with slideshow, watermark and image zoom; **image galleries** in blog posts
- 📝 **Blog** with full-text search, tags, **newsletter subscription** (double opt-in), **share buttons** (privacy-friendly) and — optionally — **comments & emoji reactions** for members (moderatable)
- 🔒 **Members area**: password-protected file area per user (optionally on an SMB share), optional **self-registration** (email confirmation + admin approval), **self-service password reset** and **per-member games toggle**
- 📨 **Contact form** with spam protection (honeypot + captcha + rate limit) and notifications via Telegram/email and **Home Assistant**
- 🧭 **Navigation bar** in the header with jump links to the sections that exist
- 📈 **Home Assistant sensors & notifications**, RSS, PWA, SEO (sitemap/robots.txt), backup & static export

## Quick start

1. Install and start the add-on
2. Set `username` and `password` in the add-on options
3. Open the admin panel (sidebar or `http://<host>:17761`)
4. Fill in your profile, add content, choose a design
5. The public site runs on `http://<host>:17760` — publish it e.g. via a Cloudflare Tunnel

> **Tip:** Only expose port 17760 to the outside. Keep the admin panel (17761) on your local network or behind HA.

Full documentation of all options and features is in [DOCS.md](DOCS.md).

> **No Home Assistant?** MyPage also runs as a plain Docker container (via `docker compose`) — guide: [STANDALONE.en.md](STANDALONE.en.md).

## Ordering & hiding sections

In the admin panel under **Content** every section is a collapsible card:

- **Reorder:** drag by the handle (⠿) on the left — works with **mouse and touch**. The homepage applies the order instantly.
- **Hide/show:** use the **eye icon** to hide a section from the homepage. Its **content is kept** and can be shown again anytime. Hidden sections also disappear from the navigation bar.
- The **header** (profile/image) always stays at the top, the **contact form** always at the bottom.
- **Projects**, **Blog** and **Library** can be positioned too (they are edited in their own tabs).

## 📅 Booking calendar / appointment button

MyPage does **not** include its own calendar — it links to an **external booking service of your choice** — ideal for coaches, consultants, tradespeople, hairdressers, etc. How to set it up:

1. **Create a booking link** with a service of your choice, e.g.:
   - [Calendly](https://calendly.com) — `https://calendly.com/yourname/30min`
   - [Cal.com](https://cal.com) — `https://cal.com/yourname`
   - Microsoft Bookings, TidyCal, SimplyBook.me, Acuity … (any public booking link works)
2. In the admin panel **→ Design tab**, fill the **"Appointment / booking link"** field with that URL.
3. Optional: customize the **"Booking button label"** field (default: *Book appointment* / *Termin buchen*).
4. **Save.**

Result: a button with a **calendar icon** appears in the homepage header (next to the support button). Clicking it opens the booking service in a **new tab**.

- If **no link** is set, **no button** is shown.
- The link must start with `http://` or `https://`, otherwise it is discarded.
- **Privacy:** nothing is loaded in advance — only the click opens the external booking page. If you use the service, mention it in your privacy policy (the provider processes the appointment data).

## Custom CSS — examples

The Design tab has a **"Custom CSS"** field. Rules entered there are included **after**
the default design and override it selectively — so you can tweak the look without
breaking the base design. Format: `selector { property: value; }`.

> **Finding class names:** on the public page press **F12** → right-click an element →
> "Inspect". The name shown there is what you target in CSS.
> Invalid CSS is ignored by the browser — the page won't break.

```css
/* Larger hero heading with letter spacing */
.hero h1 { font-size: 2.6rem; letter-spacing: 1px; }

/* Rounder project and album cards with a shadow */
.card, .album-card { border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,.2); }

/* More space above each section heading */
.section-title { margin-top: 48px; }

/* Fill skill chips with the accent color */
.skill { background: var(--accent); color: #fff; border-color: var(--accent); }

/* Square avatar instead of round */
.avatar { border-radius: 12px; }

/* Italic tagline */
.tagline { font-style: italic; }

/* Lift project cards more on hover */
.card:hover { transform: translateY(-6px); }
```

You can use **design variables** (they adapt to light/dark automatically):
`var(--accent)`, `var(--text)`, `var(--muted)`, `var(--surf)` (card background),
`var(--bg)` (page background), `var(--border)`.

For security, `<` characters are stripped from the field — so only CSS is possible, no HTML/script.
