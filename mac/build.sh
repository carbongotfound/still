#!/bin/sh
# Builds Still.app, Still-<version>.dmg and Still-mac.zip with xcodebuild. Run on a Mac with Xcode 15 or newer: sh mac/build.sh
#  ARCH=arm64  one architecture, for quick builds (default: universal, arm64 and x86_64)
#  QA=1        a test build with the QA channel (-D STILL_QA) into build/qa/, no dmg. Never distribute it.
set -eu
cd "$(dirname "$0")"
repo=..
version=$(sed -n 's:.*<Version>\(.*\)</Version>.*:\1:p' "$repo/still/Still.csproj")
# still/Shell ships as committed, so it must be built from this still-ui: the hash of still-ui's files (as vite.config.ts
# works it out) has to match the one the interface build left in still/Shell/source.txt.
ui=$(cd "$repo/still-ui" && find . \( -name node_modules -o -name dist \) -prune -o -type f -print | LC_ALL=C sort |
 while IFS= read -r f; do printf '%s\n' "$f"; tr -d '\r' < "$f"; done | shasum -a 256 | cut -c1-64)
if [ "$ui" != "$(tr -d '\r\n' < "$repo/still/Shell/source.txt" 2>/dev/null)" ]; then
 echo "still/Shell is older than still-ui: run npm run build in still-ui and commit still/Shell" >&2; exit 1
fi
out=build flags="" id=com.carbongotfound.still
# QA builds keep their WebKit data, caches and defaults apart from the real app (~/Library/*/com.carbongotfound.still.qa).
if [ "${QA:-0}" = 1 ]; then out=build/qa flags="-D STILL_QA" id=com.carbongotfound.still.qa; fi
app=$out/Still.app
resources=$app/Contents/Resources

# Derived data stays in $out/dd between builds, so a rebuild only compiles what changed.
xcodebuild -scheme Still -configuration Release -destination "generic/platform=macOS" -derivedDataPath "$out/dd" \
 ARCHS="${ARCH:-arm64 x86_64}" ONLY_ACTIVE_ARCH=NO OTHER_SWIFT_FLAGS="$flags" -quiet build
bin=$out/dd/Build/Products/Release/Still

rm -rf "$app" "$out/Still.iconset"
mkdir -p "$app/Contents/MacOS" "$app/Contents/Frameworks" "$resources"
cp "$bin" "$app/Contents/MacOS/Still"
# Sparkle, the updater: its framework (with its installer and helper apps) goes in Frameworks, where the app looks for it.
ditto "$out/dd/Build/Products/Release/Sparkle.framework" "$app/Contents/Frameworks/Sparkle.framework"
otool -l "$app/Contents/MacOS/Still" | grep -q "@executable_path/../Frameworks" || install_name_tool -add_rpath @executable_path/../Frameworks "$app/Contents/MacOS/Still"
cp -R "$repo/still/Shell" "$resources/Shell"
cp "$repo/still/Assets/Readability.js" "$repo/still/Assets/LoginObserver.js" "$resources/"
cp -R "$repo/still/Assets/roles" "$resources/roles"
cp -R "$repo/still/Assets/skills" "$resources/skills"
cp "$repo/still/Assets/setup.md" "$repo/still/Assets/make.md" "$resources/"
cp "$repo/LICENSE" "$repo/THIRD-PARTY-NOTICES.txt" "$resources/"
cp -R "$repo/Licenses" "$resources/Licenses"

# Scripts and lists come straight from the Windows app, so both stay in step: extract <const> from a C# file into <file>.
extract() {
 awk -v start="const string $2 = \"\"\"" 'index($0, start) {on=1; next} on && /^ *""";/ {exit} on' "$repo/still/$1" > "$resources/$3"
 test -s "$resources/$3"
}
awk '/BlockedDomains = \[/ {on=1; next} on && /^ *\];/ {exit} on' "$repo/still/MainWindow.Actions.cs" | grep -o '"[^"]*"' | tr -d '"' > "$resources/blocked.txt"
test -s "$resources/blocked.txt"
for name in Page Snapshot Find Click Watch Mark Seen Same Focus Scroll Wait Sensitive FileInput Cursor Mask Sig; do extract MainWindow.Agents.cs "${name}Js" "agent-$name.js"; done
for name in Results Readable; do extract MainWindow.Lookup.cs "${name}Js" "lookup-$name.js"; done
extract MainWindow.Drafts.cs DraftScript draft.js

iconset=$out/Still.iconset
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
 sips -z $size $size "$repo/still/Assets/still.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
 double=$((size * 2))
 sips -z $double $double "$repo/still/Assets/still.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$resources/Still.icns"
rm -rf "$iconset"

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
 <key>CFBundleName</key><string>Still</string>
 <key>CFBundleDisplayName</key><string>Still</string>
 <key>CFBundleIdentifier</key><string>$id</string>
 <key>CFBundleExecutable</key><string>Still</string>
 <key>CFBundleIconFile</key><string>Still</string>
 <key>CFBundlePackageType</key><string>APPL</string>
 <key>CFBundleShortVersionString</key><string>$version</string>
 <key>CFBundleVersion</key><string>$version</string>
 <key>LSMinimumSystemVersion</key><string>12.0</string>
 <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
 <key>NSHighResolutionCapable</key><true/>
 <key>NSSupportsAutomaticGraphicsSwitching</key><true/>
 <key>SUFeedURL</key><string>https://github.com/carbongotfound/still/releases/latest/download/appcast.xml</string>
 <key>SUPublicEDKey</key><string>egV3LKSaF1DAgZRrNAKlXY2XeXA68G8SbBGOd/W1rzU=</string>
 <key>SUEnableAutomaticChecks</key><false/>
 <key>SUAllowsAutomaticUpdates</key><true/>
 <key>SUAutomaticallyUpdate</key><true/>
 <key>NSAppTransportSecurity</key><dict><key>NSAllowsArbitraryLoadsInWebContent</key><true/></dict>
 <key>NSCameraUsageDescription</key><string>Websites you allow can use your camera, for example for video calls.</string>
 <key>NSMicrophoneUsageDescription</key><string>Websites you allow can use your microphone, for example for calls.</string>
 <key>NSLocationUsageDescription</key><string>Websites you allow can use your location.</string>
 <key>CFBundleURLTypes</key>
 <array>
  <dict>
   <key>CFBundleURLName</key><string>Web site URL</string>
   <key>CFBundleURLSchemes</key><array><string>http</string><string>https</string></array>
  </dict>
 </array>
 <key>CFBundleDocumentTypes</key>
 <array>
  <dict>
   <key>CFBundleTypeName</key><string>Web page</string>
   <key>CFBundleTypeRole</key><string>Viewer</string>
   <key>LSItemContentTypes</key><array><string>public.html</string><string>public.xhtml</string></array>
  </dict>
 </array>
</dict>
</plist>
PLIST

# Ad-hoc signed: macOS asks once on first launch (right-click > Open). See mac/README.md. Sparkle accepts an ad-hoc signed
# update when its EdDSA signature matches SUPublicEDKey above; the release workflow signs Still-mac.zip and writes appcast.xml.
codesign --force --deep --sign - "$app"
if [ "$out" = build/qa ]; then echo "Built $app ($version, QA)"; exit 0; fi

ditto -c -k --keepParent "$app" "$out/Still-mac.zip"
staging=$out/dmg
rm -rf "$staging" "$out/Still-$version.dmg"
mkdir -p "$staging"
cp -R "$app" "$staging/"
ln -s /Applications "$staging/Applications"
hdiutil create -quiet -volname Still -srcfolder "$staging" -format UDZO "$out/Still-$version.dmg"
rm -rf "$staging"
echo "Built $app and $out/Still-$version.dmg ($version)"
