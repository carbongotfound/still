#!/bin/sh
# Builds a universal Still.app and Still-mac.zip. Run on a Mac with Xcode 15 or newer: sh mac/build.sh
set -eu
cd "$(dirname "$0")"
repo=..
version=$(sed -n 's:.*<Version>\(.*\)</Version>.*:\1:p' "$repo/still/Still.csproj")
app=build/Still.app
resources=$app/Contents/Resources

swift build -c release --arch arm64 --arch x86_64
bin=$(swift build -c release --arch arm64 --arch x86_64 --show-bin-path)

rm -rf build
mkdir -p "$app/Contents/MacOS" "$resources"
cp "$bin/Still" "$app/Contents/MacOS/Still"
cp -R "$repo/still/Shell" "$resources/Shell"

# The blocked domains and the YouTube ad script come straight from the Windows app, so both stay in step.
awk '/BlockedDomains = \[/ {on=1; next} on && /^ *\];/ {exit} on' "$repo/still/MainWindow.Actions.cs" | grep -o '"[^"]*"' | tr -d '"' > "$resources/blocked.txt"
awk '/const string YouTubeAdScript = """/ {on=1; next} on && /^ *""";/ {exit} on' "$repo/still/MainWindow.Actions.cs" > "$resources/youtube.js"
test -s "$resources/blocked.txt" && test -s "$resources/youtube.js"

iconset=build/Still.iconset
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
 sips -z $size $size "$repo/still/Assets/still.png" --out "$iconset/icon_${size}x${size}.png" >/dev/null
 double=$((size * 2))
 sips -z $double $double "$repo/still/Assets/still.png" --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$resources/Still.icns"

cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
 <key>CFBundleName</key><string>Still</string>
 <key>CFBundleDisplayName</key><string>Still</string>
 <key>CFBundleIdentifier</key><string>com.carbongotfound.still</string>
 <key>CFBundleExecutable</key><string>Still</string>
 <key>CFBundleIconFile</key><string>Still</string>
 <key>CFBundlePackageType</key><string>APPL</string>
 <key>CFBundleShortVersionString</key><string>$version</string>
 <key>CFBundleVersion</key><string>$version</string>
 <key>LSMinimumSystemVersion</key><string>12.3</string>
 <key>LSApplicationCategoryType</key><string>public.app-category.productivity</string>
 <key>NSHighResolutionCapable</key><true/>
 <key>NSSupportsAutomaticGraphicsSwitching</key><true/>
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

codesign --force --deep --sign - "$app"
ditto -c -k --keepParent "$app" build/Still-mac.zip
echo "Built $app ($version)"
