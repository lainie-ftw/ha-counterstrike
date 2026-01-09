# HTML Structure Analysis: Team Page vs Liquipedia:Matches

## Summary
The team page "Upcoming Matches" section uses a **carousel-based vertical card layout**, which is completely different from the **horizontal div-based layout** used on the Liquipedia:Matches page.

## Team Page (Upcoming Matches) Structure

### Navigation Path
```
<div data-switch-group-container="countdown">
  └── <div class="carousel">
      └── <div class="carousel-content">
          └── <div class="carousel-item">  (one per match)
              └── <div class="match-info match-info--vertical">
```

### Match Container Structure
```html
<div class="match-info match-info--vertical">
  ├── <div class="match-info-top-row">
  │   └── <span class="match-info-countdown">
  │       └── <span class="timer-object" data-timestamp="1768006800">
  │
  ├── <div class="match-info-tournament">
  │   └── <span class="match-info-tournament-wrapper">
  │       └── <span class="match-info-tournament-name">
  │           └── <a href="/tournament/link" title="Tournament Name">
  │
  └── <div class="match-info-header match-info-header-vertical">
      ├── <div class="match-info-opponent-row">  (Team 1)
      │   ├── <div class="match-info-opponent-identity">
      │   │   └── <div class="block-team">
      │   │       ├── <span class="team-template-image-icon">
      │   │       │   └── <a href="/counterstrike/TeamName">
      │   │       │       └── <img src="/path/to/logo.png">
      │   │       └── <span class="name">
      │   │           └── <a href="/counterstrike/TeamName">TeamName</a>
      │   └── <span class="match-info-opponent-score">  (empty for upcoming)
      │
      └── <div class="match-info-opponent-row">  (Team 2 - same structure)
```

## Liquipedia:Matches Page Structure

### Navigation Path
```
<div data-toggle-area-content="1">  (1=upcoming, 2=completed)
  └── <div class="new-match-style">
```

### Match Container Structure
```html
<div class="new-match-style">
  ├── <span class="timer-object" data-timestamp="...">
  │
  ├── <div class="match-info">
  │   ├── <div class="match-info-header">
  │   │   ├── <div class="match-info-header-opponent-left">
  │   │   │   └── <div class="block-team">
  │   │   │       ├── <span class="name">
  │   │   │       │   └── <a href="/counterstrike/Team">
  │   │   │       └── <img src="/logo.png">
  │   │   │
  │   │   ├── <div class="match-info-header-scoreholder">
  │   │   │
  │   │   └── <div class="match-info-header-opponent"> (right team)
  │   │       └── <div class="block-team"> (same as left)
  │   │
  │   └── <div class="match-info-tournament">
  │       └── <span class="league-icon-small-image">
  │           └── <a title="Tournament Name">
```

## Key Differences

| Feature | Team Page | Liquipedia:Matches |
|---------|-----------|-------------------|
| Container | `match-info match-info--vertical` | `new-match-style` |
| Layout | Carousel with items | Toggle area with divs |
| Teams | `match-info-opponent-row` (2x) | `match-info-header-opponent-left` + `match-info-header-opponent` |
| Tournament | `match-info-tournament-name` | `league-icon-small-image` |
| Timer | Inside `match-info-top-row` | Direct child of container |
| Score holder | `match-info-opponent-score` (per team) | `match-info-header-scoreholder` (shared) |

## Implementation Strategy

1. **For Upcoming Matches**: Use team page
   - URL: `https://liquipedia.net/counterstrike/{team_name}`
   - Find: `<div data-switch-group-container="countdown">`
   - Navigate: `carousel` → `carousel-content` → `carousel-item` (first one)
   - Parse: `match-info-vertical` structure

2. **For Completed Matches**: Keep existing logic
   - URL: `https://liquipedia.net/counterstrike/Liquipedia:Matches`
   - Find: `<div data-toggle-area-content="2">`
   - Parse: `new-match-style` structure (existing code)

3. **Shared Data Points**:
   - Timer: `span.timer-object[data-timestamp]`
   - Teams: `block-team` → `span.name` → `a` (text + href)
   - Logos: `block-team` → `img` (src)
   - Tournament: Tournament name from link title attribute
