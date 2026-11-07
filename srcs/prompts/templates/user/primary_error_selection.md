You are analyzing a DAQ system failure. Select the single PRIMARY root-cause error
from the list below. Use this cascade hierarchy:

PRIMARY (hardware/readout failure at source):
  - CAENV1730: "wrong event size", "CAEN_DGTZ_ReadData returns -1"
  - PhysCrateData: "Too many times (10) with zero data size in TileHeader"
  - BernCRTData: "Failed to initialise febdrv on interface"
  - SPECTDCTimestampReader: "Critical error in getData_()"
  - ICARUSTriggerV3: "Was not able to initialize SPEXI"
  - NevisTPC: "DMA timed out", conflicting trigger sources
  - General: any hardware-level failure, bad data from digitizer/readout

SECONDARY (consequence of primary, buffer/memory issue):
  - Buffer overflows from upstream corrupted data
  - "Redzone was overwritten" / memory corruption
  - "PoolBuffer is empty" / "PoolBuffer is full"
  - Worker thread crashes
  - "Inconsistent event numbers" (PhysCrateData)
  - "Header out of sync" (NevisTPC)

TERTIARY (downstream timeout/cascade effects):
  - "FragmentBuffer timeout"
  - "event counter reset" / sequence errors
  - "Causality problem" / timestamp violations
  - "There is no data for %d seconds" (NevisTPC)
  - "Detected a gap in the channel N sample sequence" (SPECTDCTimestampReader)

Error list:
{error_list}{doc_section}

Return JSON with: primary_error_filename (board name or filename),
primary_error_message (first 80 chars of the error message),
reasoning (one sentence).
