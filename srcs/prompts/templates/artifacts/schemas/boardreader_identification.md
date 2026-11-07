## Boardreader Identification Artifact

Identifies boardreader types, components, and key error messages from DAQ logs.

### Fields

- `boardreader_types` (list[string], required): Boardreader/generator types identified in the
  logs. Known types organized by subsystem:
  - **Common**: DummyGenerator, SpectraTimeReadout, WhiteRabbitReadout, CAENV1730Readout,
    BernCRTData, BernCRTZMQData, BernCRT_GeneratorBase
  - **ICARUS**: PhysCrateData, PhysCrateFakeData, PhysCrate_GeneratorBase, ICARUSTriggerUDP,
    ICARUSTriggerV2, ICARUSTriggerV3, CRT::FragGen
  - **SBND**: MBBReader, WIBReader, TriggerBoardReader, SPECTDCTimestampReader,
    CAENV1740Readout, NevisTPCData, NevisTPCFile, NevisTPCCALIB, NevisTPCNUXMIT,
    NevisTPC2StreamNUandSNXMIT, NevisTB_generatorBase, NevisTBStream
- `components` (list[string], required): Additional component names found in logs
  (e.g., "FragmentBuffer", "WorkerThread", "PoolBuffer", "CircularBuffer", "FEBDRV",
  "XMITReader", "ControllerModule", "TriggerModule", "DataBlock", "DataRange")
- `error_messages` (list[string], required): Key error messages to match against documentation

### JSON Format

```json
{
    "boardreader_types": [
        "CAENV1730Readout", "PhysCrateData", "BernCRTData",
        "ICARUSTriggerV3", "SPECTDCTimestampReader",
        "NevisTPC2StreamNUandSNXMIT"
    ],
    "components": [
        "FragmentBuffer", "WorkerThread", "PoolBuffer", "CircularBuffer",
        "FEBDRV", "XMITReader", "ControllerModule", "TriggerModule",
        "DataBlock", "DataRange"
    ],
    "error_messages": ["CAENReadData() tried to write N bytes into M-byte buffer"]
}
```
