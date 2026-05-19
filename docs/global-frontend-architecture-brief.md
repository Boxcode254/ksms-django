# Global Frontend Architecture Brief
**Kenya School Management System (KSMS)**
*Prepared for UX/UI review — May 2026*

---

## 1. Base Layout & Navigation Structure

### base.html Structure

The single `templates/base.html` is the only layout shell. It renders as:

```
<html>
  <head>   ← Tailwind CSS, Google Fonts (Inter + Outfit), PWA manifest
  <body hx-boost="true">
    ├── #global-loading-indicator   ← thin 3px top progress bar (HTMX events)
    ├── .min-h-screen (lg:flex when authenticated)
    │   ├── <aside>                 ← 280px sticky sidebar (desktop only, lg+)
    │   │   ├── Logo / brand mark
    │   │   ├── <nav>               ← role-branched sidebar links
    │   │   └── bottom: Password + Logout
    │   └── <div class="flex-1">
    │       ├── <header>            ← sticky topbar with mobile menu + user pill
    │       │   ├── hamburger → .ksms-mobile-drawer (off-canvas overlay)
    │       │   └── role badge + avatar initial
    │       ├── #global-banner-region  ← Django messages toast stack
    │       └── <main>              ← {% block content %}
    └── (unauthenticated: simple topbar + max-w-7xl centered main)
```

### Navigation Handling

**It is one global nav file with heavy `{% if %}` branching — not separate per-role files.** Inside `base.html` there are five distinct nav sections:

| Role condition | What renders |
|---|---|
| `user.is_admin_role or user.is_teacher_role` | Full "Operations" group: Students, Academics, Attendance, CBC Reports, Reports. Finance sub-items gated further by `user.is_admin_role`. |
| `user.is_student_role` | "My Learning" group: Report Card, Timetable. |
| `user.is_parent_role` | "Family" group: My Invoices only. |
| `user.is_superuser` | "Governance" group: Audit Logs, Django Admin. |
| Unauthenticated | Public topbar with Login / Create account CTAs. |

The desktop sidebar is `hidden lg:block` (280px fixed column). Mobile navigation is a separate off-canvas drawer (`ksms-mobile-drawer`) triggered by a "Menu" button in the sticky header. **The mobile drawer duplicates all of the sidebar HTML verbatim**, leading to two copies of the full nav tree in every HTML response.

Expandable groups use native `<details>/<summary>` elements with the custom `.ksms-nav-group` class, auto-opened server-side when `ns == 'academics'` etc.

---

## 2. View & Routing Architecture

### URL Structure

All apps are registered flat at root level (`path('', include('students.urls'))`), with only `reports/` and `cbc/` having a URL prefix. There is no role-based URL separation — a single URL space serves all roles.

```
/              → core (home, dashboard, audit logs)
/accounts/     → django-allauth (login, signup, password reset)
/students/     → students app (admin + teacher)
/academics/    → academics app (admin + teacher)
/attendance/   → attendance app (admin + teacher)
/finance/      → finance app (admin, parent read-only)
/reports/      → reports app (admin/teacher write, student read own)
/cbc/          → cbc app
/communication/→ communication app
/admin/        → Django admin (superuser)
```

### Role Enforcement Pattern

Access control uses a **mixin-based, unified-views architecture** — not separate apps per role.

The `core/authz.py` module provides:
- `RoleRequiredMixin` — checks `user.role` against `allowed_roles`, raises `403` on failure.
- `RolePermissionRequiredMixin` — combines role check + Django object-level permission check.
- `role_required()` decorator — function-based view equivalent.

Each app defines local alias mixins:
```python
# academics/views.py
class AcademicModuleReadMixin(RolePermissionRequiredMixin):
    allowed_roles = (User.Role.SCHOOL_ADMIN, User.Role.TEACHER)

class AcademicModuleAdminWriteMixin(RolePermissionRequiredMixin):
    allowed_roles = (User.Role.SCHOOL_ADMIN,)
```

The `DashboardView` dispatches to **four separate dashboard templates** (`admin_dashboard.html`, `teacher_dashboard.html`, `student_dashboard.html`, `parent_dashboard.html`) via `get_template_names()`, while sharing one view class and one URL. Each template gets role-specific context from `_admin_context()`, `_teacher_context()`, etc.

### HTMX Integration

Most list + form views support **HTMX partial renders** via a `HtmxTemplateMixin` pattern:
```python
class HtmxTemplateMixin:
    htmx_template_name = None  # e.g. "students/partials/student_results.html"
    def get_template_names(self):
        if htmx and not boosted:
            return [self.htmx_template_name]
        return [self.template_name]
```
Filter forms submit via `hx-get` to swap only the results container, without a full page reload. Most list views have a paired partial template (e.g. `student_results.html`) and a full-page wrapper (`student_list.html`).

---

## 3. Reusable UI Components (Tables & Forms)

### Tables

There is **no reusable table component or template tag**. Every table is hand-written per page with repeated Tailwind utility chains:

```html
<!-- Repeated verbatim across 8+ templates -->
<div class="rounded-3xl border border-slate-200 bg-white shadow-sm overflow-hidden">
  <div class="overflow-x-auto">
    <table class="w-full text-sm text-slate-700">
      <thead class="border-b border-slate-100 bg-slate-50">
        <tr>
          <th class="px-5 py-3 text-left text-xs font-semibold text-slate-500">...</th>
        </tr>
      </thead>
      <tbody>
        <tr class="border-b border-slate-50 hover:bg-slate-50">
          <td class="px-5 py-3 ...">...</td>
        </tr>
      </tbody>
    </table>
  </div>
</div>
```

**Pagination** is also copy-pasted across every list template. No `{% include %}` partial is used for the pagination block.

### Forms

Forms fall into two patterns:

1. **Filter forms** — wrapped in `<div class="ksms-filter">` which applies CSS-level styling to child inputs via descendant selectors in `styles.css`. No Django form rendering library is used; fields are iterated with `{% for field in form %}`.

2. **Create/Edit forms** — styled in Python via a `StyledFieldsMixin` pattern that loops over `self.fields.values()` in `__init__` and manually applies a long Tailwind class string to each widget:
```python
INPUT_CLASS = (
    "block w-full rounded-2xl border border-slate-300 bg-white px-4 py-3 "
    "text-sm text-slate-900 shadow-sm outline-none transition focus:border-sky-500 "
    "focus:ring-2 focus:ring-sky-200"
)
```
This means **form widget classes are defined in Python**, not templates, and are spread across `students/forms.py`, `academics/forms.py`, `finance/forms.py`, etc. Changes to a global input style require editing every `forms.py` file.

**No crispy-forms, widget-tweaks, or form inclusion tags are used.** The `templates/account/` files use a `{% load form_tags %}` template tag with a custom `|add_class` filter for allauth forms only.

### Inconsistency between form styles

Report/filter forms use `ksms-filter` CSS-scope styling (rounded-xl, `border-slate-300`), while student/guardian create-edit forms use `rounded-2xl` widgets with sky-500 focus rings. These are visually similar but technically inconsistent and defined in different places.

---

## 4. Global Tailwind & Styling Configuration

### Setup

The project uses **django-tailwind** with Tailwind CSS v4** (`@import "tailwindcss"`) in `theme/static_src/src/styles.css`. There is no `tailwind.config.js` — Tailwind v4 uses CSS-first configuration.

Content scanning is done via:
```css
@source "../../../**/*.{html,py,js}";
```

### Custom Tokens

A CSS custom property palette is defined in `:root`:

| Token | Value | Semantic meaning |
|---|---|---|
| `--ksms-bg` | `#F8FAFC` (slate-50) | Page background |
| `--ksms-ink` | `#0F172A` (slate-900) | Body text |
| `--ksms-muted` | `#64748B` (slate-500) | Secondary text |
| `--ksms-border` | `#E2E8F0` (slate-200) | Border default |
| `--ksms-surface` | `#FFFFFF` | Card/input background |
| `--ksms-brand` | `#2563EB` (blue-600) | Primary CTA / active state |
| `--ksms-brand-strong` | `#1D4ED8` (blue-700) | Hover state |
| `--ksms-brand-soft` | `#EFF6FF` (blue-50) | Soft tint background |

Two Google Fonts are loaded: **Inter** (body) and **Outfit** (`.ksms-display` headings).

### Defined Component Classes

The `@layer components` block defines a solid set of reusable classes:

| Class | Purpose |
|---|---|
| `.ksms-display` | Outfit font for headings |
| `.ksms-card`, `.ksms-card-soft` | Surface cards |
| `.ksms-btn`, `.ksms-btn-primary/secondary/soft/danger` | Button variants |
| `.ksms-kpi` | KPI metric tiles on dashboards |
| `.ksms-item-card` | Hover-interactive list cards |
| `.ksms-sidebar-link`, `.ksms-sub-link` | Sidebar nav links |
| `.ksms-nav-group`, `.ksms-nav-chevron` | Collapsible nav groups |
| `.ksms-filter` | Scopes CSS to style filter form inputs |
| `.ksms-progress-bar` | HTMX page-load indicator |
| `.ksms-mobile-overlay`, `.ksms-mobile-drawer` | Off-canvas mobile nav |
| `.ksms-list-grid` | Responsive 1→2→3 column grid |

### Bloated / Inconsistent Patterns

**1. Corner radius inconsistency.** The CSS components use `0.75rem` (`rounded-xl`) but templates freely use `rounded-2xl`, `rounded-3xl`, `rounded-full` inline. There is no enforced radius scale.

**2. Shadow inconsistency.** `.ksms-card` defines `box-shadow: 0 1px 3px...` but templates use `shadow-xl shadow-slate-200/60` inline — a much heavier shadow. Both coexist on the same page.

**3. `rounded-3xl border border-slate-200 bg-white p-6 shadow-xl shadow-slate-200/60`** — this 8-token chain is the most repeated string in the template layer, appearing in nearly every page's main content card. It is never extracted into `.ksms-card` in CSS (`.ksms-card` uses `rounded-xl` and `shadow-sm`, so they are not the same).

**4. Inline `{% if %}` color logic in templates.** Status badge color selection (`bg-emerald-100 text-emerald-700` / `bg-red-100 text-red-700` etc.) is repeated 10+ times across attendance, finance, and student tables. No badge component exists.

**5. Button style inconsistency.** `ksms-btn` classes are used on dashboards; individual app templates use long inline chains like `rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700` which are functionally equivalent to `.ksms-btn.ksms-btn-primary` but never use those classes.

**6. Duplicate mobile nav HTML.** The desktop sidebar nav tree and the mobile drawer nav tree are separate, duplicated HTML blocks in `base.html`. Approximately 120 lines of navigation HTML exist twice per page response.

---

## Summary for UX Expert

| Area | Current state | Recommended action |
|---|---|---|
| Nav architecture | One file, role-branched `{% if %}` | Extract per-role nav includes; eliminate mobile/desktop duplication with one shared partial |
| Tables | Hand-coded per page, no reuse | Create `_table.html` partial + `_pagination.html` partial |
| Forms (filter) | `.ksms-filter` CSS scope works | Standardise; remove duplicate filter block patterns |
| Forms (create/edit) | Widget classes in Python per-app | Centralise `StyledFieldsMixin` into one `core/forms.py` |
| Card component | Two competing definitions (`.ksms-card` vs inline `rounded-3xl shadow-xl`) | Resolve to one `.ksms-card-elevated` variant |
| Status badges | Inline `{% if %}` colour chains everywhere | Create `{% badge status %}` template tag |
| Button usage | Mixed `.ksms-btn` classes + long inline chains | Enforce `.ksms-btn` everywhere; remove inline equivalents |
| Radius / shadow scale | Undefined; freeform usage | Document and enforce a 3-level token scale (sm / md / lg) |
