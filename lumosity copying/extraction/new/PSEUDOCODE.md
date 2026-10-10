# game.wasm: what was recovered (Masterpiece assembly)

Method: found `Il2CppCodeGenModule` for `Masterpiece.dll` in the wasm data section (540 methods, 539 with code),
matched its method-pointer array to the IL2CPP metadata method table (per-type method counts sum to exactly 540;
the same check passes for CugShared.Pillar = 3766 and CogUnityGamesSharedCore = 974), mapped table index -> wasm function,
then disassembled each function. Full output: `masterpiece_disasm.wat`; name map: `masterpiece_methods.json`.

CAVEATS
- Pseudocode below is translated BY HAND from the disassembly. It is not machine-decompiled output.
- Field names are not recovered (only byte offsets such as `this+92`); the metadata field table was not decoded.
  Names in comments are guesses from the identifier list and are marked (?).
- Only the Masterpiece module was dumped. The same method works for the other game modules.

## Referee.CalculatePoints(int x)           wasm func 115429
```
pts = this[92] * x;                       // int multiplier field (?) times x
if (this[84] == true)                     // isRoundUpToTen (?)
    pts = RoundUpToTen(pts);
    if (this[220]) Debug.Log("Referee.calculatePoints: rounded " ...);   // debug-only logging
return pts;
```
## Referee.RoundUpToTen(float v)             func 115438
```
return (int) (Math.Ceiling(v * 0.1f) * 10f);
```
## Referee.NextScoreLevel(float current, float target)   func 115427
Adaptive-difficulty step with different rates for moving up and down:
```
float min = (float) this[72];                         // minimum level
float t   = (current > target) ? current + (target - current) / this[124]   // slower/faster when above target
                               : target;
float next = current + (t - current) * this[128];     // exponential smoothing toward t
return Math.Max(next, min);
```
## Referee.InterpolateResponseTime(int level = -1)       func 115421
```
if (level == -1) level = this[16];                    // current level
int r = (level - this[72]) / (this[76] - this[72]);   // INTEGER division as compiled: min-max normalisation
int t = (int) Math.Floor(r * (this[212] - this[208]) + this[208]);   // secondsAtMinLevel..secondsAtMaxLevel (?)
this[196] = this[200] / (float) t;
this[216] = (int) (t * 2.5f);                         // second threshold = 2.5 x the interpolated time
return t;
```
## SpatialReasoningReferee.Penalty(int score, int moves, int budget, bool enabled)   func 115725
```
int pen = 0;
if (enabled && moves > budget)
    pen = (int)(10f * (100 / budget)) * (budget - Math.Min(moves, 2 * budget));   // negative number
return Math.Max(-score, pen);                          // never take more than the current score
```
i.e. each move over budget costs 10*(100/budget) points, counted for at most `budget` extra moves.
## SpatialReasoningReferee.PerfectRotationBonus()        func 115724
```
return (int) Math.Round(this.referee[116] * this[104]);   // float * int, banker's rounding
```
## SpatialReasoningReferee.AddMove()                      func 115691
```
this[136] = this[128];
moves = ++this[80];
if (this[112]) { UpdateRotationBonus(); this[26] = (this[28] != 0); }
else           { this[92] = 0; }                       // clears the multiplier used by CalculatePoints
this[25] = (this[48] < moves) ? this[26] : true;        // over-budget flag (?)
```
## Other functions with real numeric constants (see .wat)
- `SpatialReasoningReferee.NextTrialLevel` (func 115629): constants 3000, 80, 100, 10
- `Referee.SetupResponseTime` (func 115433): 1000.0 (ms->s), 100
- `Referee.GetLevelUpFraction` (func 115430), `Referee.Accelerate` (func 115423)
- `SnapToPoint.FindNear` / `CheckPieceProximity` (funcs 115340 / 115348): snapping logic; CheckPieceProximity is wrapped in try/catch via `invoke_*`
