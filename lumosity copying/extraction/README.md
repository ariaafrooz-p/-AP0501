# Unity bundle export

Source: cug-shared-assets.bundle, cug-shared-pillar.bundle, scene.bundle
Layers: Brotli -> UnityFS (LZ4HC directory, uncompressed data block) -> SerializedFile v23 (+ .resource streams)
Engine version is stripped in the build; parsed with a Unity 6 (6000.0.0f1) fallback.

raw/    Carved container nodes (SerializedFiles and .resource streams), byte-exact. Usable in AssetStudio/AssetRipper.
media/  audio/*.m4a (30, named), textures/*.png, fonts/*.ttf, sprites_svg/*.svg (geometry only; atlas textures not in bundles),
        textassets/ (7 localization JSON: ja ko de en pt es fr)
dump/   Every object (4,879 + 246 + 4,792 = 9,917) as typetree JSON, one JSONL per type per bundle.
        _hierarchy.txt   scene/prefab trees with components, positions, sizes
        _container.txt   original asset paths (Packages/com.lumoslabs...) and dependencies
