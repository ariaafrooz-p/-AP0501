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
