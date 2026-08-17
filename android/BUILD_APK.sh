#!/usr/bin/env bash
# ============================================================
# OmniAI Android - ملف بناء APK النهائي
# يبني app-release.apk (موقّع بمفتاح debug للتجربة) أو app-debug.apk
# المتطلبات: JDK 17+, Android SDK (platforms;android-35, build-tools;35.0.0)
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

# 1) تحديد مسار Android SDK
if [ -z "${ANDROID_HOME:-}" ]; then
  for d in "$HOME/Android/Sdk" "$HOME/android-sdk" "/usr/local/lib/android/sdk"; do
    [ -d "$d" ] && export ANDROID_HOME="$d" && break
  done
fi
[ -z "${ANDROID_HOME:-}" ] && { echo "ERROR: Android SDK not found. Set ANDROID_HOME."; exit 1; }
echo "sdk.dir=$ANDROID_HOME" > local.properties
echo "Using SDK: $ANDROID_HOME"

# 2) تثبيت مكونات SDK الناقصة تلقائياً إن وُجد sdkmanager
SDKMANAGER="$ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager"
if [ -x "$SDKMANAGER" ]; then
  yes | "$SDKMANAGER" --licenses >/dev/null 2>&1 || true
  "$SDKMANAGER" "platforms;android-35" "build-tools;35.0.0" "platform-tools" >/dev/null
fi

# 3) عنوان الخادم (يُمرر كمتغير بيئة، الافتراضي emulator loopback)
API_BASE_URL="${OMNIAI_API_URL:-http://10.0.2.2:8000/}"
echo "API base URL: $API_BASE_URL"

# 4) البناء
GRADLE="gradle"; command -v gradle >/dev/null || GRADLE="./gradlew"
BUILD_TYPE="${1:-debug}"   # debug أو release
if [ "$BUILD_TYPE" = "release" ]; then
  $GRADLE clean assembleRelease --no-daemon
  APK="app/build/outputs/apk/release/app-release.apk"
else
  $GRADLE clean assembleDebug --no-daemon
  APK="app/build/outputs/apk/debug/app-debug.apk"
fi

echo "============================================================"
echo "APK جاهز: $APK"
ls -lh "$APK"
echo "للتثبيت على جهازك: adb install -r \"$APK\"  أو انسخ الملف للهاتف وافتحه"
