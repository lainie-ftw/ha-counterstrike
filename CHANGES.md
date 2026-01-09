# HTML Structure Changes - January 9, 2026

## Summary
Updated the Counter-Strike match scraper to work with Liquipedia's new div-based HTML structure (previously table-based).

## Changes Made

### 1. **HTML Structure Migration**
   - **Old Structure**: Table-based layout with `<td class="team-left">`, `<td class="team-right">`, `<td class="versus">`, etc.
   - **New Structure**: Div-based layout with `<div class="new-match-style">`, `<div class="match-info-header">`, etc.

### 2. **DOM Navigation Updates**
   - **Old**: Navigate from `<a>` tag through `span -> span -> td -> tr -> tbody -> table`
   - **New**: Navigate from `<a>` tag through `span -> div.block-team -> div.match-info-header-opponent -> div.match-info-header -> div.match-info -> div.new-match-style`

### 3. **Section Identifier Changes**
   - **Upcoming matches**: Still `data-toggle-area-content="1"`
   - **Completed matches**: Changed from `"3"` to `"2"`

### 4. **Class Name Changes**

#### Team Information:
- **Old**: `<td class="team-left">` and `<td class="team-right">`
- **New**: `<div class="match-info-header-opponent-left">` and `<div class="match-info-header-opponent">`
- **Team name**: Now in `<span class="name">` instead of `<span class="team-template-text">`

#### Score/Versus Section:
- **Old**: `<td class="versus">` with simple text like "vs" or "2:1"
- **New**: `<div class="match-info-header-scoreholder">` with nested structure:
  - `<span class="match-info-header-scoreholder-upper">` contains score or "vs"
  - `<span class="match-info-header-scoreholder-lower">` contains match format (Bo3, Bo5, etc.)

#### Tournament Information:
- **Old**: `<td class="match-filler">`
- **New**: `<div class="match-info-tournament">`

#### Streams Section:
- **New**: Added `<div class="match-info-streams">` section (fallback for stream detection)

### 5. **Files Updated**
1. **test_scraper.py** - Standalone test script updated with new structure
2. **custom_components/counterstrike/__init__.py** - Home Assistant integration updated

## Testing

The scraper has been tested with:
- ✅ Upcoming matches (e.g., `Eternal_Fire`)
- ✅ Completed matches (e.g., `GamerLegion`)
- ✅ Score extraction for completed matches
- ✅ Tournament information extraction
- ✅ Team logo and link extraction

## Usage

Test the scraper standalone:
```bash
python3 test_scraper.py <team_name> [upcoming|completed]

# Examples:
python3 test_scraper.py Eternal_Fire
python3 test_scraper.py GamerLegion completed
```

## Notes

- The new structure is more semantic and uses modern div-based layouts
- Match status detection still works using the score holder text content
- Winner detection uses CSS classes on the match container
- Stream/VOD extraction logic remains largely unchanged
- All existing functionality has been preserved
