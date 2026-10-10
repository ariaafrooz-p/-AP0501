# Unity WebGL build teardown

## Container layers
- game_data.br  -> Brotli -> UnityWebData1.0 container (14.4 MB) -> 6 files
- game_wasm.br  -> Brotli -> game.wasm (59.2 MB, valid WebAssembly MVP)
- data.unity3d  -> UnityFS v8, LZ4HC, 82 blocks -> 6 serialized files (10.7 MB)
- Engine: Unity 6000.5.2f1, serialized-file version 23, platform 20 (WebGL), no type trees (release build)
- Scripting backend: IL2CPP (code is inside the wasm; metadata is global-metadata.dat, version 107)

## Serialized files (objects by class)
- globalgamemanagers: 20 managers/settings (PlayerSettings, InputManager, QualitySettings, ResourceManager, BuildSettings...)
- globalgamemanagers.assets: 2717 MonoScript, 28 MonoBehaviour, 24 Shader, 4 Texture2D, 2 AnimationClip(72?), misc
- resources.assets: 64 MonoBehaviour, 48 GameObject, 48 RectTransform, 34 CanvasRenderer, 10 TextAsset, 8 Texture2D, 5 Material, 3 Sprite, 2 Canvas, 1 Shader
- level0: one scene (camera, 2 GameObjects, 3 MonoBehaviours); sharedassets0.assets: tiny
- Resources_unity_builtin_extra: 46 built-in shaders

## What the app is
A suite of cognitive-assessment mini-games (namespaces LumosLabs.*, package ids com.lumoslabs.pillar / sharedassets) using a PureMVC-style architecture (Cmd/Note/Controller/Model/View).
Games found as assemblies: MemoryMatch, MemoryMatrix, MemoryServes, OrganicOrder, OutOfSorts, Masterpiece, LostInMigration, MagicChance,
plus Assessments (ArithmeticReasoning, DigitSymbolCoding, ... 282 classes) with consent / demographics / login / survey / finish states.
Shared: CogUnityGamesSharedCore (AssetBundleManager, AppInterface/WebAppInterface, RuntimeGamesManifest, AppParameters), NativeKeyboard, DOTween, Coffee.UIParticle, Newtonsoft.Json.
Most game content is NOT in this build: it is loaded at runtime as asset bundles (runtime_manifest.json, asset_bundle_path, StreamingAssets URL).

## Data files (TextAssets)
- sensors.json: 23 shape definitions (Parallelogram, Polyiamond4x/5x, Triangle, Monarc, Diarc...) - polygon vertex lists
- silhouettes_csv.txt: 5151 puzzle silhouettes, rows like `id,Shape:rot:x:y;Shape:rot:x:y` (Masterpiece tangram-style game)
- silhouettes.bytes / levels.bytes (+ _test): binary, bit-packed (BitReader class exists in Masterpiece assembly)
- Unity housekeeping: PerformanceTestRunInfo/Settings JSON (build was made with Unity 6000.5/staging), TMP line-breaking lists

## Textures (decoded to PNG in tex/)
12 textures: Unity splash logo (2048x1024 DXT5), debug font, 5 MuseoSans TMP SDF atlases (1024^2, weights 100/300/500/700/900),
on-screen-keyboard icons (done/backspace/shift), LUT + Bayer matrix.

## wasm
150,281 functions, 49.4 MB code, 8.8 MB data. 591 imports (582 env, 9 wasi). 596 exports; game-facing: SendMessage, SendMessageString, SendMessageNumber,
SetFullscreen, SendPasteEvent, GetCopyBufferAsCStr, ReleaseKeys, getMetricsInfo, profiler hooks.
106 JS_* bridge imports (WebRequest, Sound, FileSystem_Sync, WebCam, WebGPU setup, MobileKeyboard, StreamingAssets URL...).
No hardcoded game-server URLs in the strings; only Unity docs / schema URLs.

## Telemetry keys visible in metadata strings (what the app records)
response_time_{mean,median_correct,exgaussian_mu/sigma/tau,mad_correct,slope,...}, trial_num_correct, challenge_{mistakes,net_correct,game_mode,seed_used,stats},
game_slug, game_mode, game_theme, level_start/end/selected, skip_tutorial_timestamp, game_crash_*, perfect_mode, no_input_timer, auto_play / auto_play_performance.

## Not done / limits
- MonoBehaviour field values are not decoded (no type trees in release builds).
- IL2CPP metadata v107 header not fully parsed; no Il2CppDumper available offline, so no full method/field dump.
- wasm not decompiled; only structure, imports/exports and strings.

---
# Addendum: framework.js + unity_full_export.zip

## framework.js (game_framework_js.br)
Despite the .br name this file is plain, uncompressed JavaScript (451 KB): Emscripten glue + a custom `Module.CUG` block and plugin functions.
- Host-page contract: the game calls `window.dispatchReactUnityEvent(name, payload)` for
  onUnityLoaded, onGameLoaded(slug), onSessionStarted(json), onCurrentSessionData(json), onSessionEnded(json), onGameActionTriggered(type), onGameExited(json).
  (the host page is a React app; if the dispatcher is missing, the game falls back to `SendMessage("AppInterface","LoadGame","{}")`.)
- Page -> game: `SendMessage("AppInterface","RequestPauseState",0|1)` on window focus/blur, `SoundStateBridge` mute sync (`OnWebMuteStateChanged`), `NativeKeyboardManager` callbacks for an off-screen <input> used as soft keyboard.
- Housekeeping: blocks arrow/backspace/delete default on canvas, tracks focus, force-loses the WebGL context on exit to free GPU memory, IDBFS mounted at /idbfs for PlayerPrefs.
- No hardcoded network URLs.

## unity_full_export.zip (307 files, 46 MB)
A prior export of three runtime asset bundles, with type trees parsed (9,917 objects):
- cug-shared-assets: shared audio (16 clips), MuseoSans fonts (ttf + SDF), 48 SVG sprites, textures
- cug-shared-pillar: shared UI/animation framework ("Pillar"): 233 container entries, 1,565 MonoBehaviours, 109 animation clips, 7 localization files (ja ko de en pt es fr)
- scene: the **Masterpiece** game scene (Packages/com.lumoslabs.masterpiece/Scenes/Masterpiece.unity): 1,141 GameObjects, 955 MonoBehaviours, 99 sprites, 14 audio clips
Bundles are Brotli -> UnityFS -> SerializedFile v23; raw CAB files are in raw/ and open in AssetStudio/AssetRipper.

## Masterpiece, decoded
- Spatial-reasoning puzzle: drag tangram-like pieces into a shaded silhouette; rotate with on-screen buttons; fewer rotations = more points; HINT button.
- 23 piece types (Triangle1/11/20/40/41, Square, Parallelogram, Monarc0/1, Diarc0-6, Polyiamond40-42/50-53), geometry from PolygonCollider2D (extract/piece_colliders.json, pieces_sheet.png).
- silhouettes_csv.txt (5,151 puzzles) = `n,Piece:rotation:x:y;Piece:...`, 1 to 9 pieces each (most are 7-8). I rendered samples (extract/silhouettes_sample.png) and they come out as valid connected silhouettes, which confirms the format. First field is a repeated small integer (grouping/difficulty), not a unique id.
- sensors.json = per-piece interior sample points (likely the coverage/overlap check). Referee / SpatialReasoningReferee classes exist in the Masterpiece assembly.
- Session config: 4 trials in a normal game, 1 in short game; metadata spec "Masterpiece", app-stat key `piece_max`, concurrent trials/responses-without-trials disallowed. Score controller counter "Score", starts at 0. AutoPlay (QA bot) skips tutorial, 0.5 s delays.
- Tutorial: 4 steps (tutor_0..3). Game strings in 7 languages. Feedback tiers: GREAT / PERFECT.
- Audio: pickup0-3, drop, tileRotate, woodSlide, hint, chimes_AnswerCorrect/Excellent/Perfect, ambient wind chimes.
- Architecture: PureMVC-style (PuzzleController/PuzzleView/PuzzleModel, Cmd/Note classes), service locator (ServicesManager with Audio, Input, Localization, ModelStore, Messenger, ThemeAssets, DynamicAssets services).

## Still not done
- Other seven games' scenes are not in either upload (only Masterpiece's scene bundle), so only Masterpiece is decoded to the content level.
- Scoring formula / hint logic live in IL2CPP code in game.wasm; not decompiled.

---
# Addendum 2: game.wasm decoded (Masterpiece assembly)
See PSEUDOCODE.md. Summary:
- IL2CPP metadata v107 is a compact custom layout (not stock). Recovered: string literals table (15,776), identifier blob (93,607 names),
  type table (12,418 types, 64 B packed, name@0, method_count@40), method table (85,439, name@0), image table (77).
- Located Il2CppCodeGenModule structs in wasm data for Masterpiece.dll / CugShared.Pillar.dll / CogUnityGamesSharedCore.dll;
  method counts match metadata exactly (540 / 3766 / 974), so method name -> wasm function mapping is reliable.
- Wrote a wasm disassembler (wasmdis.py) and dumped all 539 Masterpiece functions (masterpiece_disasm.wat).
- Hand-translated scoring / adaptive-difficulty functions to pseudocode (PSEUDOCODE.md): CalculatePoints, RoundUpToTen, NextScoreLevel,
  InterpolateResponseTime, Penalty (over-budget move penalty), PerfectRotationBonus, AddMove.
- Remaining gaps: field names, the other assemblies' code (same method applies), true decompilation to C#.
