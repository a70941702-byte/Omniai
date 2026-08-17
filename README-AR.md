# رفع OmniAI على GitHub وبناء APK سحابياً — خطوات من المتصفح

1. افتح https://github.com/new من متصفح هاتفك وسجّل دخولك
2. اسم المستودع: omniai — اختار Public — اضغط Create
3. اضغط "uploading an existing file"
4. ارفع كل محتويات هذه الحزمة (مجلد android و .github و README)
5. اضغط Commit changes
6. من تبويب Actions ← اختار "Build OmniAI APK" ← اضغط "Run workflow"
7. بعد ~5-10 دقائق: افتح التشغيلة المكتملة ← حمّل Artifact باسم OmniAI-debug-apk
8. فك الضغط وثبّت app-debug.apk على هاتفك
