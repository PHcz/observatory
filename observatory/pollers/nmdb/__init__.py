"""NMDB / NEST neutron-monitor poller package (Phase 13, MU2-06).

An isolated hourly oneshot poller that caches the Oulu neutron monitor's counts/s
(NEST ``output=ascii``, ``yunits=0``) into SQLite — the global cosmic-ray reference
the dashboard overlays against local muon flux. See README.md for the citation /
acceptable-use note and the deploy migration reminder.
"""
