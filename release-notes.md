# v1.1.0 - Breaking Change Release

## Breaking Changes

### Site selection now uses hierarchical precedence

**BREAKING**: The site filter logic has been changed from additive to hierarchical. The most specific selection now takes exclusive precedence.

**Before (v1.0.1 and earlier)**: Selecting individual sites, suburbs, and cities combined all matching sites together (union/additive behavior). Selecting one site in Adelaide would return that site PLUS all sites from any selected suburbs and cities.

**After (v1.1.0)**: Only the most specific selection is used:
- Individual sites selected - ONLY those specific sites are included (suburb and city selections are ignored)
- No individual sites but suburbs selected - ONLY sites within those suburbs (city selections are ignored)
- No individual sites or suburbs but cities selected - ONLY sites within those cities
- No selections - all sites (unchanged)

**Impact**: Users who previously selected individual sites may see devices and entities removed from Home Assistant if those sites were only included due to the additive parent region behavior.

**Action Required**: If you want sites from multiple regions, reconfigure the integration via Settings > Devices & Services > SA Fuel Pricing > Configure and explicitly select all desired cities, suburbs, or individual sites at the appropriate level.

---

# v1.0.1 - Bugfix Release

## Fixes

### Release workflow zip structure and contents

- Fixed the release workflow packaging to correctly structure the zip file for HACS installation
- The initial fix changed into `custom_components/` before zipping, but still included `sa_fuel_pricing/` in the zip path
- HACS would extract this as `custom_components/sa_fuel_pricing/custom_components/sa_fuel_pricing/`
- The workflow now changes into `custom_components/sa_fuel_pricing/` and zips the contents directly, so the zip archive contains `__init__.py`, `manifest.json`, etc. at its root
- When HACS extracts into `custom_components/sa_fuel_pricing/`, the files are placed correctly without any path duplication
