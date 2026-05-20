# Football Dashboard Project Rules

## Core Architecture

* Main frontend is HTML/CSS/JS only.
* Do NOT migrate to React or other frameworks.
* Preserve existing backend and CSV workflow.
* Preserve Railway cloud sync compatibility.

## Critical Features That Must Never Break

* cloud save/load
* localStorage persistence
* picks_history.csv persistence
* BTTS support
* bankroll calculations
* editable tables
* filters
* renderAll flow
* history merge logic
* GitHub sync logic

## UI/UX Direction

* Compact professional operational dashboard
* Minimal scrolling
* App-like multi-page structure
* Desktop-first but fully responsive
* Mobile optimized
* High information density
* Avoid oversized cards/buttons
* Reduce whitespace
* Dashboard should feel like:

  * trading terminal
  * sportsbook control panel
  * analytics platform

## Dashboard Structure

Pages:

* Home
* Picks
* History
* Analytics
* Manual Bets
* Settings

## Home Page Philosophy

Home should ONLY show:

* summary metrics
* ROI
* profit
* exposure
* streaks
* quick charts

Do NOT place giant tables on Home.

## Picks Philosophy

Operational page.
Compact tables/cards.
Fast execution workflow.

## History Philosophy

Historical analysis only.
Paginated/filterable.

## Analytics Philosophy

No duplicated analytics sections.
Keep analytics modular and compact.

## NBA

NBA backend/scripts may remain in repository.
NBA content should NOT appear in current dashboard UI.

## CSS Rules

* Avoid duplicate CSS
* Prefer compact spacing
* Optimize for laptop screens
* Avoid unnecessary vertical space

## JavaScript Rules

* Use defensive DOM guards
* Never assume elements exist
* Avoid breaking render flow
* Preserve current business logic

## Preferred Refactor Strategy

* incremental improvements
* avoid rewrites
* preserve stable logic
* prioritize UX compactness and maintainability
