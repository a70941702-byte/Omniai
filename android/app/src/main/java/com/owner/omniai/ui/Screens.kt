package com.owner.omniai.ui

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import com.owner.omniai.data.Approval
import com.owner.omniai.viewmodel.MainViewModel
import kotlinx.coroutines.launch
import java.util.Locale

@Composable
fun LoginScreen(vm: MainViewModel = viewModel()) {
    var token by remember { mutableStateOf("") }
    var server by remember { mutableStateOf("https://your-server.example.com/api/v1/") }
    val error by vm.loginError.collectAsState()

    Column(
        Modifier.fillMaxSize().padding(32.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("OmniAI", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold)
        Text("مساعدك الشخصي — أنت تملكه", color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(32.dp))
        OutlinedTextField(
            value = server, onValueChange = { server = it },
            label = { Text("رابط الخادم (Server URL)") }, singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(Modifier.height(12.dp))
        OutlinedTextField(
            value = token, onValueChange = { token = it },
            label = { Text("رمز المالك (Owner Token)") }, singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )
        error?.let {
            Spacer(Modifier.height(8.dp))
            Text(it, color = MaterialTheme.colorScheme.error)
        }
        Spacer(Modifier.height(24.dp))
        Button(onClick = { vm.login(token, server) }, modifier = Modifier.fillMaxWidth()) {
            Text("اتصال")
        }
        Spacer(Modifier.height(16.dp))
        Text(
            "الرمز موجود في backend/data/owner_token.txt على خادمك",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatScreen(vm: MainViewModel, onNavigate: (String) -> Unit) {
    val messages by vm.messages.collectAsState()
    val sending by vm.sending.collectAsState()
    val conversations by vm.conversations.collectAsState()
    val toast by vm.toast.collectAsState()
    var input by remember { mutableStateOf("") }
    var drawerOpen by remember { mutableStateOf(false) }
    val listState = rememberLazyListState()
    val snackbar = remember { SnackbarHostState() }
    val context = LocalContext.current

    val speechLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            val spoken = result.data?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            spoken?.firstOrNull()?.let { input = it }
        }
    }
    fun speechIntent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ar-SA")
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ar-SA")
        putExtra(RecognizerIntent.EXTRA_PROMPT, "اتكلم دلوقتي…")
    }
    val micPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted -> if (granted) runCatching { speechLauncher.launch(speechIntent()) } }
    fun startListening() {
        if (!SpeechRecognizer.isRecognitionAvailable(context)) return
        if (context.checkSelfPermission(Manifest.permission.RECORD_AUDIO) == android.content.pm.PackageManager.PERMISSION_GRANTED) {
            runCatching { speechLauncher.launch(speechIntent()) }
        } else micPermission.launch(Manifest.permission.RECORD_AUDIO)
    }

    var tts by remember { mutableStateOf<TextToSpeech?>(null) }
    var speakEnabled by remember { mutableStateOf(true) }
    DisposableEffect(Unit) {
        var engine: TextToSpeech? = null
        engine = TextToSpeech(context) { status ->
            if (status == TextToSpeech.SUCCESS) {
                engine?.language = Locale("ar")
                tts = engine
            }
        }
        onDispose { engine?.stop(); engine?.shutdown() }
    }
    LaunchedEffect(messages.size) {
        if (speakEnabled && messages.isNotEmpty()) {
            val last = messages.last()
            if (last.role != "user") tts?.speak(last.content, TextToSpeech.QUEUE_FLUSH, null, "omniai_reply")
        }
    }

    LaunchedEffect(Unit) { vm.loadConversations() }
    LaunchedEffect(messages.size) {
        if (messages.isNotEmpty()) listState.animateScrollToItem(messages.size - 1)
    }
    LaunchedEffect(toast) { toast?.let { snackbar.showSnackbar(it); vm.clearToast() } }

    ModalNavigationDrawer(
        drawerState = rememberDrawerState(if (drawerOpen) DrawerValue.Open else DrawerValue.Closed)
            .also { LaunchedEffect(drawerOpen) { if (drawerOpen) it.open() else it.close() } },
        drawerContent = {
            ModalDrawerSheet {
                Text("المحادثات", Modifier.padding(16.dp), fontWeight = FontWeight.Bold)
                TextButton(onClick = { vm.newConversation(); drawerOpen = false }) {
                    Icon(Icons.Default.Add, null); Spacer(Modifier.width(8.dp)); Text("محادثة جديدة")
                }
                HorizontalDivider()
                LazyColumn {
                    items(conversations) { c ->
                        NavigationDrawerItem(
                            label = { Text(c.title, maxLines = 1) },
                            selected = false,
                            onClick = { vm.openConversation(c.id); drawerOpen = false }
                        )
                    }
                }
            }
        }
    ) {
        Scaffold(
            snackbarHost = { SnackbarHost(snackbar) },
            topBar = {
                TopAppBar(
                    title = { Text("OmniAI") },
                    navigationIcon = {
                        IconButton(onClick = { drawerOpen = true }) {
                            Icon(Icons.Default.Menu, "القائمة")
                        }
                    },
                    actions = {
                        IconButton(onClick = {
                            speakEnabled = !speakEnabled
                            if (!speakEnabled) tts?.stop()
                        }) {
                            Icon(
                                if (speakEnabled) Icons.Default.VolumeUp else Icons.Default.VolumeOff,
                                if (speakEnabled) "الصوت مفعّل" else "الصوت مغلق"
                            )
                        }
                        IconButton(onClick = { onNavigate("system") }) { Icon(Icons.Default.Info, "النظام") }
                        IconButton(onClick = { onNavigate("approvals") }) { Icon(Icons.Default.CheckCircle, "الموافقات") }
                        IconButton(onClick = { onNavigate("controls") }) { Icon(Icons.Default.Settings, "التحكم") }
                    }
                )
            }
        ) { pad ->
            Column(Modifier.fillMaxSize().padding(pad)) {
                LazyColumn(
                    state = listState,
                    modifier = Modifier.weight(1f).fillMaxWidth(),
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    items(messages) { m ->
                        val isUser = m.role == "user"
                        Row(
                            Modifier.fillMaxWidth(),
                            horizontalArrangement = if (isUser) Arrangement.End else Arrangement.Start
                        ) {
                            Surface(
                                shape = MaterialTheme.shapes.large,
                                color = if (isUser) MaterialTheme.colorScheme.primaryContainer
                                        else MaterialTheme.colorScheme.surfaceVariant,
                                modifier = Modifier.widthIn(max = 300.dp)
                            ) {
                                Column(Modifier.padding(12.dp)) {
                                    Text(m.content)
                                    if (!isUser && m.modelId != null) {
                                        Text(
                                            "model ${m.modelId.take(8)}",
                                            style = MaterialTheme.typography.labelSmall,
                                            color = MaterialTheme.colorScheme.onSurfaceVariant
                                        )
                                    }
                                }
                            }
                        }
                    }
                    if (sending) {
                        item { CircularProgressIndicator(Modifier.padding(16.dp).size(24.dp)) }
                    }
                }
                Row(
                    Modifier.fillMaxWidth().padding(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    OutlinedTextField(
                        value = input, onValueChange = { input = it },
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("اسأل أي حاجة…") },
                        maxLines = 4
                    )
                    Spacer(Modifier.width(4.dp))
                    IconButton(onClick = { startListening() }) {
                        Icon(Icons.Default.Mic, "تحدث", tint = MaterialTheme.colorScheme.primary)
                    }
                    FilledIconButton(
                        onClick = { vm.send(input); input = "" },
                        enabled = input.isNotBlank() && !sending
                    ) { Icon(Icons.Default.Send, "إرسال") }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SystemScreen(vm: MainViewModel) {
    val status by vm.status.collectAsState()
    val models by vm.models.collectAsState()
    val cycles by vm.cycles.collectAsState()
    val toast by vm.toast.collectAsState()
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(Unit) { vm.refreshSystem() }
    LaunchedEffect(toast) { toast?.let { snackbar.showSnackbar(it); vm.clearToast() } }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = { TopAppBar(title = { Text("النظام والتدريب") }) }
    ) { pad ->
        LazyColumn(
            Modifier.fillMaxSize().padding(pad).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("الحالة", fontWeight = FontWeight.Bold)
                        status?.let { s ->
                            Text("النموذج الحالي: ${s.current_model?.take(8)} (v${s.current_model_version})")
                            Text("حلقة التدريب: ${if (s.training_thread_alive) "تعمل" else "متوقفة"}")
                            Text("النماذج: ${s.counts["models"]}  •  الذكريات: ${s.counts["memories"]}  •  " +
                                 "الدورات: ${s.counts["cycles"]}  •  موافقات معلقة: ${s.counts["pending_approvals"]}")
                        } ?: Text("جاري التحميل…")
                    }
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { vm.runTrainingCycle() }) { Text("تشغيل دورة") }
                    OutlinedButton(onClick = { vm.startTraining() }) { Text("تشغيل تلقائي") }
                    OutlinedButton(onClick = { vm.stopTraining() }) { Text("إيقاف") }
                }
            }
            item { Text("النماذج", fontWeight = FontWeight.Bold) }
            items(models) { m ->
                Card(Modifier.fillMaxWidth()) {
                    Row(
                        Modifier.fillMaxWidth().padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text("v${m.version} • ${m.id.take(10)}", fontFamily = FontFamily.Monospace)
                            Text(
                                m.status + ((m.metrics as? Map<*, *>)?.get("overall")?.let { "  •  overall=$it" } ?: ""),
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        if (m.status != "current") {
                            TextButton(onClick = { vm.rollback(m.id) }) { Text("تراجع") }
                        }
                    }
                }
            }
            item { Text("الدورات الأخيرة", fontWeight = FontWeight.Bold) }
            items(cycles.take(10)) { c ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp)) {
                        Text("دورة #${c["cycle_no"]} — ${c["status"]}", fontWeight = FontWeight.SemiBold)
                        Text("المرحلة: ${c["phase"]}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ApprovalsScreen(vm: MainViewModel) {
    val approvals by vm.approvals.collectAsState()
    val toast by vm.toast.collectAsState()
    val snackbar = remember { SnackbarHostState() }

    LaunchedEffect(Unit) { vm.loadApprovals() }
    LaunchedEffect(toast) { toast?.let { snackbar.showSnackbar(it); vm.clearToast() } }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = { TopAppBar(title = { Text("الموافقات المعلقة") }) }
    ) { pad ->
        LazyColumn(
            Modifier.fillMaxSize().padding(pad).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            if (approvals.isEmpty()) {
                item { Text("لا يوجد شيء بانتظار قرارك") }
            }
            items(approvals) { a -> ApprovalCard(a, vm) }
        }
    }
}

@Composable
fun ApprovalCard(a: Approval, vm: MainViewModel) {
    var expanded by remember { mutableStateOf(false) }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(a.kind.replace('_', ' '), fontWeight = FontWeight.Bold)
            Text(a.payload["change"]?.toString() ?: "", style = MaterialTheme.typography.bodyMedium)
            TextButton(onClick = { expanded = !expanded }) {
                Text(if (expanded) "إخفاء التفاصيل" else "عرض التقرير الكامل")
            }
            if (expanded) {
                val fields = listOf(
                    "reason" to "السبب", "benefit" to "الفائدة",
                    "affected_files" to "الملفات", "test_results" to "الاختبارات",
                    "performance_before_after" to "الأداء", "risks" to "المخاطر",
                    "resources_required" to "الموارد", "estimated_cost" to "التكلفة"
                )
                fields.forEach { (k, label) ->
                    a.payload[k]?.let { v ->
                        Text("$label:", fontWeight = FontWeight.SemiBold,
                             style = MaterialTheme.typography.labelLarge)
                        Text(v.toString(), style = MaterialTheme.typography.bodySmall,
                             fontFamily = FontFamily.Monospace)
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Button(onClick = { vm.decide(a, "approved") }) { Text("موافقة") }
                OutlinedButton(onClick = { vm.decide(a, "rejected") }) { Text("رفض") }
                OutlinedButton(onClick = { vm.decide(a, "more_tests") }) { Text("اختبارات إضافية") }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ControlsScreen(vm: MainViewModel) {
    val controls by vm.controls.collectAsState()
    val memories by vm.memories.collectAsState()
    val toast by vm.toast.collectAsState()
    val snackbar = remember { SnackbarHostState() }
    var newMemory by remember { mutableStateOf("") }

    LaunchedEffect(Unit) { vm.loadControls(); vm.loadMemories() }
    LaunchedEffect(toast) { toast?.let { snackbar.showSnackbar(it); vm.clearToast() } }

    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        topBar = { TopAppBar(title = { Text("تحكم المالك") }) }
    ) { pad ->
        LazyColumn(
            Modifier.fillMaxSize().padding(pad).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item { Text("الصلاحيات", fontWeight = FontWeight.Bold) }
            val toggles = listOf(
                "training_enabled" to "التدريب المستمر",
                "learning_enabled" to "التعلم من المحادثات",
                "internet_enabled" to "الوصول للإنترنت",
                "external_models_enabled" to "نماذج ذكاء خارجية",
                "code_edit_enabled" to "تعديل الكود ذاتياً",
                "install_deps_enabled" to "تثبيت مكتبات",
                "server_enabled" to "استخدام خادم GPU",
                "gpu_enabled" to "كرت الشاشة GPU",
                "autonomous_cycles" to "دورات تلقائية"
            )
            items(toggles) { (key, label) ->
                val value = controls[key] as? Boolean ?: false
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(label)
                    Switch(checked = value, onCheckedChange = { vm.setControl(key, it) })
                }
            }
            item {
                Spacer(Modifier.height(8.dp))
                Text("حدود الموارد", fontWeight = FontWeight.Bold)
            }
            items(listOf("cpu_limit_percent", "ram_limit_mb", "storage_limit_mb", "budget_credits")) { key ->
                val value = (controls[key] as? Number)?.toInt() ?: 0
                var text by remember(key, value) { mutableStateOf(value.toString()) }
                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(key.replace('_', ' '), Modifier.weight(1f))
                    OutlinedTextField(
                        value = text, onValueChange = { text = it.filter(Char::isDigit) },
                        modifier = Modifier.width(110.dp), singleLine = true
                    )
                    TextButton(onClick = { text.toIntOrNull()?.let { vm.setControl(key, it) } }) {
                        Text("حفظ")
                    }
                }
            }
            item {
                Spacer(Modifier.height(8.dp))
                Text("الذاكرة (${memories.size})", fontWeight = FontWeight.Bold)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(
                        value = newMemory, onValueChange = { newMemory = it },
                        modifier = Modifier.weight(1f),
                        placeholder = { Text("علّمني معلومة…") }, singleLine = true
                    )
                    TextButton(onClick = { if (newMemory.isNotBlank()) { vm.addMemory(newMemory); newMemory = "" } }) {
                        Text("إضافة")
                    }
                }
            }
            items(memories.take(30)) { m ->
                Card(Modifier.fillMaxWidth()) {
                    Row(
                        Modifier.fillMaxWidth().padding(12.dp),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(m.text, maxLines = 2, style = MaterialTheme.typography.bodySmall)
                            Text(m.kind, style = MaterialTheme.typography.labelSmall,
                                 color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        IconButton(onClick = { vm.forget(m.id) }) {
                            Icon(Icons.Default.Delete, "نسيان",
                                 tint = MaterialTheme.colorScheme.error)
                        }
                    }
                }
            }
        }
    }
}
