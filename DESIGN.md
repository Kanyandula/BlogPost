# NyasaBlog Design System — "The Modern Savanna Editorial"

## Overview

A premium editorial design system inspired by Malawian culture. Clean, content-first, magazine-feel with warm tones and sophisticated cultural accents.

**Stitch Project:** https://stitch.withgoogle.com/projects/7016938615348696701

## Tech Stack

- **CSS Framework:** Tailwind CSS (CDN with custom config)
- **Font:** Inter (weights 100-900, via Google Fonts)
- **Icons:** Material Symbols Outlined (Google Fonts)
- **Dark Mode:** Class-based (`darkMode: "class"`)

## Color Tokens (Material Design 3)

### Primary (Deep Teal)
| Token | Hex | Usage |
|-------|-----|-------|
| `primary` | `#002627` | Text headings, active states |
| `primary-container` | `#0f3d3e` | Primary buttons, hero gradients |
| `primary-fixed` | `#beebeb` | Light teal backgrounds |
| `on-primary` | `#ffffff` | Text on primary surfaces |
| `on-primary-container` | `#7da8a8` | Text on primary-container |

### Secondary (Blue)
| Token | Hex | Usage |
|-------|-----|-------|
| `secondary` | `#4059aa` | Links, highlights, focus rings |
| `secondary-container` | `#8fa7fe` | Selection backgrounds, hover states |
| `secondary-fixed` | `#dce1ff` | Light blue backgrounds |

### Tertiary (Warm Amber/Brown)
| Token | Hex | Usage |
|-------|-----|-------|
| `tertiary` | `#321d00` | Brown text accents |
| `tertiary-container` | `#4f3000` | Category badges dark |
| `tertiary-fixed` | `#ffddb8` | Light warm backgrounds |
| `tertiary-fixed-dim` | `#ffb95f` | Amber accents, featured badges |

### Surfaces
| Token | Hex | Usage |
|-------|-----|-------|
| `surface` / `background` | `#f8f9fa` | Page background |
| `surface-container-lowest` | `#ffffff` | Elevated cards |
| `surface-container-low` | `#f3f4f5` | Subtle sections |
| `surface-container` | `#edeeef` | Default containers |
| `surface-container-high` | `#e7e8e9` | Nav, drawers |
| `surface-container-highest` | `#e1e3e4` | Highest elevation |

### Text
| Token | Hex | Usage |
|-------|-----|-------|
| `on-surface` | `#191c1d` | Primary body text (never use #000) |
| `on-surface-variant` | `#404848` | Secondary text, subtitles |

### Utility
| Token | Hex | Usage |
|-------|-----|-------|
| `outline` | `#717978` | Borders (use sparingly) |
| `outline-variant` | `#c0c8c8` | Ghost borders at 20% opacity |
| `error` | `#ba1a1a` | Error states |

## Typography

All Inter font. Hierarchy through scale and weight contrast.

| Role | Size | Weight | Color |
|------|------|--------|-------|
| Display (article titles) | `text-4xl` to `text-6xl` | `font-black` (900) | `primary` |
| Headline (section headers) | `text-2xl` to `text-3xl` | `font-bold` (700) | `primary` |
| Title (card titles) | `text-lg` to `text-xl` | `font-bold` | `primary` |
| Body | `text-base` (16px) | `font-normal` (400) | `on-surface` |
| Label / Metadata | `text-xs` to `text-sm` | `font-medium` | `on-surface-variant` |
| Category badges | `text-[10px]` to `text-xs` | `font-semibold uppercase tracking-widest` | varies |

### Drop Cap (Article pages)
```css
.drop-cap::first-letter {
  float: left;
  font-size: 5rem;
  line-height: 1;
  font-weight: 800;
  padding-right: 0.75rem;
  color: #002627;
}
```

## Spacing & Layout

- **Spacing scale:** 4px base (Tailwind default, scale factor 2)
- **Max width:** `max-w-[1440px]` for main content
- **Page padding:** `px-12` desktop, `px-6` mobile
- **Card padding:** `p-6` to `p-8`
- **Grid gap:** `gap-8` to `gap-12`
- **Section spacing:** Use `py-12` to `py-16`

## Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `DEFAULT` | `0.25rem` (4px) | Small elements |
| `lg` | `0.5rem` (8px) | Buttons, inputs |
| `xl` | `0.75rem` (12px) | Cards |
| `rounded-[10px]` | 10px | Mobile cards, images |
| `rounded-2xl` | 16px | Large cards, sidebars |
| `rounded-full` | 9999px | Pills, avatars, search |

## Design Rules

### The "No-Line" Rule
**No 1px solid borders for sectioning.** Define boundaries through:
- Background color shifts between surface tiers
- Spacing (`gap-10`, `gap-12`)
- Tonal transitions

### Glass Navigation
```
bg-[#f8f9fa] opacity-85 backdrop-blur-xl
```
Fixed, translucent navbar with blur effect.

### Shadows
- **Cards:** No drop shadows. Use tonal surface shifts instead.
- **Floating elements only:** `blur-[32px]` to `blur-[48px]`, `on-surface` at 4-8% opacity.

### Ghost Borders (inputs only)
```
border border-outline-variant/20 focus:ring-2 focus:ring-secondary/20
```

### Cultural Geometric Dividers
SVG patterns inspired by Malawian geometry between content sections:
- Color: `tertiary-fixed-dim` at 15% opacity
- Use at major thematic breaks only

## Components

### Buttons
| Type | Classes |
|------|---------|
| Primary | `bg-primary-container text-on-primary px-6 py-2.5 rounded-lg font-semibold` |
| Secondary | `bg-surface-container-high text-primary px-6 py-2.5 rounded-lg` |
| Ghost | `text-on-surface hover:bg-secondary-container/10 px-4 py-2` |
| WhatsApp | `bg-[#25D366] text-white px-6 py-2.5 rounded-lg` |

### Cards
```
bg-surface-container-lowest rounded-xl overflow-hidden
```
- No divider lines inside cards
- Use spacing to separate content blocks
- Image hover: `group-hover:scale-105 transition-transform duration-500`

### Category Badges
```
text-xs font-semibold uppercase tracking-widest
```
Colors vary by context (secondary, tertiary-fixed-dim, etc.)

### Tag Pills
```
px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm
hover:bg-secondary-container
```

### Inputs
```
bg-surface-container-lowest border border-outline-variant/20 rounded-lg py-3 px-4
focus:ring-2 focus:ring-secondary/20 focus:border-secondary
```

## Responsive Breakpoints

| Breakpoint | Behavior |
|------------|----------|
| Mobile (<768px) | Single column, bottom nav bar, hamburger menu |
| Tablet (md: 768px) | 2 columns, sidebar collapses |
| Desktop (lg: 1024px) | Full layout, sidebar visible, top nav |

### Mobile Bottom Navigation
```
fixed bottom-0 left-0 w-full bg-surface-container-lowest/90 backdrop-blur-md
rounded-t-[10px] flex justify-around py-3
```
4 tabs: Home, Search, Bookmarks, Profile

### Floating Action Button (Mobile)
```
fixed bottom-24 right-6 w-14 h-14 rounded-full bg-primary text-on-primary
```

## Screen Inventory (19 screens)

| Screen | Mobile HTML | Desktop HTML |
|--------|-------------|--------------|
| Home Feed | `home_mobile.html` | `home_desktop.html` |
| Blog Detail | `blog_detail_mobile.html` | `blog_detail_desktop.html` |
| Create Post | `create_post_mobile.html` | `create_post_desktop.html` |
| Author Profile | `author_profile_mobile.html` | `author_profile_desktop.html` |
| Login | `login_mobile.html` | `login_desktop.html` |
| Register | `register_mobile.html` | `register_desktop.html` |
| Bookmarks | `bookmarks_mobile.html` | `bookmarks_desktop.html` |
| Search Results | `search_results_mobile.html` | `search_results_desktop.html` |
| Search Empty | `search_empty_mobile.html` | `search_empty_desktop.html` |

All files in `/design_reference/` directory.

## Accessibility

- Never use pure black `#000000` — use `on-surface` (#191c1d)
- Min touch targets: 44px (`p-3` on icon buttons)
- Visible focus states: `focus:ring-2 focus:ring-secondary/20`
- Max reading width: `65ch` for article body
- High contrast text on all surfaces
- `selection:bg-secondary-container selection:text-on-secondary-container`
