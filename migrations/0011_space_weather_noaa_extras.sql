-- depends: 0010_indoor_air
-- 2026-10: extra NOAA SWPC fields on the per-poll space_weather row.
-- solar_wind_density comes from the same real-time solar wind (RTSW) feed that
-- replaced the retired products/solar-wind/plasma-2-hour.json. The rest are new
-- endpoints: RTSW magnetometer (IMF Bz/Bt), GOES >=10 MeV integral protons, and
-- the current NOAA R/S/G scale levels. All nullable: each endpoint can fail
-- independently (partial-fetch tolerance), and rows before this migration
-- simply have NULLs.

ALTER TABLE space_weather ADD COLUMN solar_wind_density REAL;   -- protons/cm^3
ALTER TABLE space_weather ADD COLUMN imf_bz_nt REAL;            -- GSM Bz, nT (negative = southward)
ALTER TABLE space_weather ADD COLUMN imf_bt_nt REAL;            -- total field, nT
ALTER TABLE space_weather ADD COLUMN proton_flux_10mev REAL;    -- GOES >=10 MeV, pfu (S1 at 10)
ALTER TABLE space_weather ADD COLUMN noaa_scale_r INTEGER;      -- radio blackout 0-5
ALTER TABLE space_weather ADD COLUMN noaa_scale_s INTEGER;      -- solar radiation storm 0-5
ALTER TABLE space_weather ADD COLUMN noaa_scale_g INTEGER;      -- geomagnetic storm 0-5
