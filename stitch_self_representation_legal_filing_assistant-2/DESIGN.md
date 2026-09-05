---
name: Civic Justice Portal
colors:
  surface: '#f9f9ff'
  surface-dim: '#cfdaf2'
  surface-bright: '#f9f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f0f3ff'
  surface-container: '#e7eeff'
  surface-container-high: '#dee8ff'
  surface-container-highest: '#d8e3fb'
  on-surface: '#111c2d'
  on-surface-variant: '#564144'
  inverse-surface: '#263143'
  inverse-on-surface: '#ecf1ff'
  outline: '#8a7174'
  outline-variant: '#ddbfc3'
  surface-tint: '#a73351'
  primary: '#6b0028'
  on-primary: '#ffffff'
  primary-container: '#8b1d3d'
  on-primary-container: '#ff9dae'
  inverse-primary: '#ffb2be'
  secondary: '#4e6073'
  on-secondary: '#ffffff'
  secondary-container: '#cfe2f9'
  on-secondary-container: '#526478'
  tertiary: '#353234'
  on-tertiary: '#ffffff'
  tertiary-container: '#4c484a'
  on-tertiary-container: '#bdb7b9'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffd9de'
  primary-fixed-dim: '#ffb2be'
  on-primary-fixed: '#400014'
  on-primary-fixed-variant: '#871a3b'
  secondary-fixed: '#d1e4fb'
  secondary-fixed-dim: '#b5c8df'
  on-secondary-fixed: '#091d2e'
  on-secondary-fixed-variant: '#36485b'
  tertiary-fixed: '#e7e1e3'
  tertiary-fixed-dim: '#cbc5c7'
  on-tertiary-fixed: '#1d1b1c'
  on-tertiary-fixed-variant: '#494648'
  background: '#f9f9ff'
  on-background: '#111c2d'
  surface-variant: '#d8e3fb'
typography:
  headline-xl:
    fontFamily: Public Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Public Sans
    fontSize: 26px
    fontWeight: '700'
    lineHeight: 34px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Public Sans
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-lg-mobile:
    fontFamily: Public Sans
    fontSize: 20px
    fontWeight: '700'
    lineHeight: 28px
  headline-md:
    fontFamily: Public Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
  body-lg:
    fontFamily: Public Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Public Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Public Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-lg:
    fontFamily: Public Sans
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Public Sans
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.02em
  label-sm:
    fontFamily: Public Sans
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.03em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  space-2xs: 0.25rem
  space-xs: 0.5rem
  space-sm: 0.75rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
  space-2xl: 2.5rem
  space-3xl: 3.5rem
  layout-margin-mobile: 1rem
  layout-margin-tablet: 1.5rem
  layout-margin-desktop: 2.5rem
  layout-sidebar-width: 16rem
  layout-content-max-width: 75rem
---

## Brand & Style

The design system embodies the authoritative, reliable, and accessible essence of Singapore's public digital judiciary infrastructure. Its primary objective is to cultivate unwavering public trust, reduce cognitive strain during legally binding proceedings, and maintain clear administrative rigor.

### Personality and Emotional Impact
- **Institutional Authority & Dignity:** Reflective of judicial sobriety and statutory dependability without feeling bureaucratic or opaque.
- **Clarity & Public Trust:** Emphasizing high legibility, predictable layout hierarchies, and high-contrast affordances to minimize citizen anxiety during formal legal submissions.
- **Civic Accessibility:** Designed to meet rigorous public accessibility expectations, ensuring every resident can complete legal self-assessments, dispute filings, and claims efficiently across any standard device.

### Visual Style
The design system adopts a **Corporate / Modern Civic** aesthetic:
- Uncluttered, light-dominant surfaces framed by institutional crimson and structured neutral borders.
- Functional callout panels with vertical accent anchors that establish immediate hierarchical priority.
- Minimalist forms and explicit interactive boundaries (soft 4px corners), avoiding trendy visual excesses such as heavy gradients, frosted glass, or diffuse multi-tier shadows.

## Colors

The palette derives directly from judicial civic identities, pairing deep institutional crimson maroon with stable slate neutrals and calibrated functional tones.

### Palette Overview
- **Primary (`#8B1D3D`):** The primary judicial maroon. Used for primary buttons, prominent screen headers, active navigation anchors, and critical informational highlight strips.
- **Secondary (`#2C3E50`):** Deep navy slate. Delivers structural grounding for secondary controls, supporting navigation icons, and inactive utility states.
- **Tertiary / Container Light (`#F8F1F3`):** Warm crimson tint. Applied to table headers, instructional panel banners, and selected assessment card states.
- **Neutral Core (`#1E293B`):** Dark slate. High-legibility text tone replacing pure black to soften eye fatigue over long statutory forms while preserving AAA contrast.
- **Surface Canvas (`#FFFFFF`):** Crisp pure white default background for cards, modals, input fields, and application viewports.
- **Surface Muted / Neutral Warm (`#F8FAFC` to `#F1F5F9`):** Subdued off-white used for instructions blocks and nested table backgrounds.
- **Border Definers (`#E2E8F0` / `#CBD5E1`):** Precise light gray boundaries delivering sharp structural separation without high cognitive noise.
- **Success / Status (`#166534`):** Forest green reserved for progress confirmation, validated fields, and successfully lodged declarations.

## Typography

The design system utilizes **Public Sans** across all roles, ensuring total harmony and adherence to civic portal design conventions. Engineered specifically for administrative clarity, its neutral vertical proportions, robust x-height, and open apertures maintain legibility across dense statutory text, tabular declarations, and interactive legal forms.

### Hierarchy & Role Allocation
- **Page Titles (`headline-xl` / `headline-lg`):** Executed in bold maroon (`#8B1D3D`) to anchor the purpose of each step in multi-stage legal workflows.
- **Section Headers & Card Titles (`headline-md`):** Deep slate (`#1E293B`) bold headings marking sub-processes, disputant options, or instruction panels.
- **Legal Form & Instruction Copy (`body-md` / `body-lg`):** Set with generous line height (1.5–1.6x) for effortless scanning of numbered conditions, disclaimers, and formal rights.
- **Input Labels & Actions (`label-lg` / `label-md`):** Medium to bold weight, often capitalized in option buttons to communicate clean, explicit choices.

## Layout & Spacing

The portal layout balances desktop productivity with step-by-step guidance, adopting an asymmetric layout consisting of an administrative sidebar alongside a focused main workflow canvas.

### Layout Geometry
- **Global Architecture:** Fixed-width 256px (`layout-sidebar-width`) left rail for global navigation (`Home`, `Resources`, procedural links) coupled with a fluid main container capped at 1200px (`layout-content-max-width`).
- **Form Panels:** Organized into clear sequential vertical tiers. Form inputs and actionable assessment cards utilize a 2-column equal split on wide displays and single-column stack on screens below 768px.
- **Spacing Rhythm:** Standard 8pt linear scale. Compact element clusters (e.g. badge icons and textual labels) sit within 8px (`space-xs`), section headers maintain 16px to 24px (`space-md` to `space-lg`) margins, and independent legal modules separate by 32px to 40px (`space-xl` to `space-2xl`).
- **Breakpoints:**
  - **Mobile (< 768px):** Sidebar collapses into an accessible top drawer navigation; form options transition into stacked full-width button rows.
  - **Tablet (768px - 1024px):** Condensed sidebar icons; dual-column form matrices scale fluidly with reduced gutters (16px).
  - **Desktop (1024px+):** Full expanded sidebar; 24px content gutters; pinned workflow progress indicator at viewport bottom.

## Elevation & Depth

To preserve an official and unambiguous demeanor, the design system minimizes heavy drop shadows. Elevation is primarily expressed through **structural ghost borders**, **crisp baseline dividing lines**, and **tonal contrast**.

### Surface Hierarchy
1. **Base Layer (Elevation 0):** Pure white (`#FFFFFF`) page canvas with optional `#F8FAFC` sectional zones.
2. **Instructional Panels (Elevation 1):** Flat, subtly tinted gray surfaces (`#F8FAFC` to `#F1F5F9`) defined by an explicit 1px neutral border (`#E2E8F0`) and an authoritative 4px solid primary maroon (`#8B1D3D`) left accent bar.
3. **Selectable Action Cards (Elevation 2):** Pure white cards bordered with 1px `#E2E8F0` resting at base. On hover and keyboard focus, elements activate a crisp 1px `#8B1D3D` perimeter border with an ultra-subtle civic resting shadow: `0 1px 3px rgba(0, 0, 0, 0.06)`.
4. **Modals & Flyouts (Elevation 3):** Clean institutional dropdowns (such as the upper login popover or language selector) feature crisp `#CBD5E1` borders and a shallow administrative shadow: `0 4px 12px rgba(15, 23, 42, 0.08)`.

## Shapes

The design system enforces a **Soft (`1`)** shape language, applying consistent `4px` (0.25rem) corner radii across interactive and structural elements.

### Corner Archetypes
- **Inputs & Standard Buttons:** Default `4px` (`rounded-sm` / `rounded-md`), establishing an orderly, predictable, and formal perimeter.
- **Assessment Choice Cards:** `4px` radius to maintain architectural stability inside grid formations.
- **Info Icon Badges & Circular Indicators:** Fully rounded (`rounded-full`, 9999px) for information badges (`i`), status dots, and civic trust symbols, distinguishing advisory markers from interactive rectangular inputs.

## Components

### Buttons
- **Primary Buttons:** Deep maroon (`#8B1D3D`) fill with `#FFFFFF` text, `4px` border radius, medium font weight (`label-lg`), and `10px 20px` internal padding. Hover shifts to `#731631`; active/pressed to `#5C1026`.
- **Secondary / Utility Buttons (e.g. Login, Cancel):** Outlined with `#8B1D3D` or neutral dark slate (`#334155`), filled with transparent or `#F8FAFC` background.
- **Disabled State:** Filled with `#CBD5E1` with `#64748B` text, suppressing all hover interactions.

### Information Panels & Callouts
- **Structure:** Encased in a soft background (`#F8FAFC`) with an explicit 4px vertical bar on the left edge in `#8B1D3D`.
- **Content:** Header incorporates an inline solid circle maroon icon (`#8B1D3D`) with a white lowercase "i", followed by numbered statutory lists styled with precise line height and prominent anchor links (crimson underline on hover).

### Selection & Option Tiles
- **Dispute Category Cards:** Wide rectangular buttons bordered by 1px `#E2E8F0` on white background.
- **Typography:** Uppercase, semi-bold `label-md` or `label-lg` dark slate text (`#1E293B`).
- **Interactive States:** On focus/hover, border colors transition to `#8B1D3D` with a tinted primary wash (`#FDF8F9`). Selected cards receive a solid 2px `#8B1D3D` stroke.

### Form Inputs & Dropdowns
- **Text Fields:** Standard height 40px, 1px `#CBD5E1` border, 4px corner radius, 12px horizontal padding. Focused inputs transition to a solid `#8B1D3D` outline with a 2px maroon focus ring at 20% opacity.
- **Required Indicators:** Crisp crimson asterisk (`*`) styled in `#8B1D3D` adjacent to labels.

### Navigation Sidebar
- **Shell:** Vertical list with clean line-item links. Left icon paired with `14px` medium font.
- **Active Navigation Item:** Highlighted with subtle crimson background tint (`#F8F1F3`) and bold `#8B1D3D` typography.

### Progress & Completion Indicators
- **Bottom Workflow Footer:** Sticky or terminal banner featuring high-contrast percentage readouts (`label-lg`), supported by a linear progress track (height 6px, track background `#E2E8F0`, progress fill `#8B1D3D` or `#2563EB`).