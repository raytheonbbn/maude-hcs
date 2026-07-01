# FTP V2 User Model Walkthrough

This walkthrough details the implementation of the V2 user model for the FTP Tgen, integrating a two-level Markov chain configuration with the Maude `UM-V2` actor architecture.

## 1. Python V2 JSON-to-Maude Converter

We implemented a new standalone parser script to convert V2 `config.json` files into `MAModel-v2` Maude definitions:
- **File:** [parsers/markovV2JsonToMaudeParser.py](file:///Users/dcirimel/pwnd2/maude-hcs/maude_hcs/parsers/markovV2JsonToMaudeParser.py)
- **Features:** 
  - Converts the hierarchical V2 format (top-level mode Markov chain, nested action Markov chains).
  - Handles the complex `JV` (Json Value) structures required by the `MAModel-v2` type (e.g. `jo(...)`, `jf(...)`).
  - **Idle State Expansion:** Automatically transforms the simple `"type": "wait"` configuration into a complete V2 state block (adding a `noop` action, setting `inter_burst_delay` from the sleep distribution, and initializing default dwell/burst steps) as expected by the UM-V2 framework.
  - **Auto-populates Initial Actions:** Infers an `initial_action` for states that don't declare one, preventing execution halts when the UM-V2 framework looks for a starting point in a new mode.
  - **Float Verification:** Ensures all numeric parameters for probability distributions (mean, std, min, max, etc.) are explicitly parsed as floats (`jf`) since the Maude random sampler (`realizeRand`) strictly expects floating point values.

## 2. Generated FTP MAModel-V2

We ran the converter against the FTP `config.json`, producing a well-formed V2 model module:
- **File:** [lib/tgen/maude/ftp/ftp-mamodel-v2.maude](file:///Users/dcirimel/pwnd2/maude-hcs/maude_hcs/lib/tgen/maude/ftp/ftp-mamodel-v2.maude)
- The generated module maps properly to `ftp-config-markov`, `ftp-config-states`, and `ftp-config-params`, successfully replicating the nested stochastic parameters for the `browse`, `upload`, `download`, and `idle` states.

## 3. Core Framework Bugfix: Tgen Actor Message Scheduling

During testing, we discovered a core bug in the shared Tgen action actor wrapper:
- **File:** [lib/common/maude/tgen-action-actor-v2.maude](file:///Users/dcirimel/pwnd2/maude-hcs/maude_hcs/lib/common/maude/tgen-action-actor-v2.maude)
- **Issue:** The `exeActionTgen` function was returning the `actionQ` message as a bare `Msg` object. When injected into the configuration by the `umv2-rcv-timeout` rule, the message remained "loose" and was ignored because the target FTP Tgen actor's receive rule (`rcvFtpAction`) specifically matches *scheduled* `ActiveMsg` format (`{T, (to ... : actionQ(...))}`).
- **Fix:** We modified `exeActionTgen` (lines 64-75) to wrap the generated `actionQ` message using the `delayMsgsX` function (which is available via `CP2-COMMON` and `DELAY-X`). This successfully translates the bare message into a scheduled message format (`[delay, msg, drop]`), which the scheduler then reliably converts into an `ActiveMsg` for the Tgen actor to process.

## 4. Full Integration Test Scenario

We created a complete test configuration that wires the User Model, the Tgen Actor, and the Server Actor together:
- **File:** [lib/tgen/maude/ftp/test-ftp-tgen-v2.maude](file:///Users/dcirimel/pwnd2/maude-hcs/maude_hcs/lib/tgen/maude/ftp/test-ftp-tgen-v2.maude)
- The test successfully demonstrates:
  1. The `UM-V2` actor initializing and spending time in the `idle` mode (using the auto-expanded noop state).
  2. Mode transitioning to `"browse"`, determining the next action (`"browse_list"`), and sending an `actionQ` message to the Tgen actor.
  3. The `FtpTgen` actor receiving the action, executing the appropriate FTP commands (`NOOP`, `PASV`, `MLSD`), and communicating with the `FtpServer`.
  4. The Tgen sending the `actionR` response back to the UM-V2 actor upon completion, allowing the User Model to schedule the next action within the burst.
- *Note:* We had to override `defaultModelTimeOut` in the test module. The FTP idle state frequently generates ~300s sleep delays, causing the standard 1000s model timeout to abort the simulation prematurely before leaving the idle state.

The V2 User Model for the FTP Tgen is now fully operational!
