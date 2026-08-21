package com.owner.omniai.viewmodel

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.owner.omniai.data.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class MainViewModel(app: Application) : AndroidViewModel(app) {
    val repo = Repository(app)

    // ---- auth ----
    private val _loggedIn = MutableStateFlow(repo.isLoggedIn)
    val loggedIn = _loggedIn.asStateFlow()
    private val _loginError = MutableStateFlow<String?>(null)
    val loginError = _loginError.asStateFlow()

    fun login(token: String, serverUrl: String) = viewModelScope.launch {
        _loginError.value = null
        repo.baseUrl = if (serverUrl.endsWith("/")) serverUrl else "$serverUrl/"
        try {
            _loggedIn.value = repo.login(token)
            if (!_loggedIn.value) _loginError.value = "Invalid token"
        } catch (e: Exception) {
            _loginError.value = "Connection failed: ${e.message}"
        }
    }

    // ---- chat ----
    data class UiMessage(val role: String, val content: String, val modelId: String? = null)
    private val _messages = MutableStateFlow<List<UiMessage>>(emptyList())
    val messages = _messages.asStateFlow()
    private val _conversationId = MutableStateFlow<String?>(null)
    val conversationId = _conversationId.asStateFlow()
    private val _sending = MutableStateFlow(false)
    val sending = _sending.asStateFlow()
    private val _conversations = MutableStateFlow<List<Conversation>>(emptyList())
    val conversations = _conversations.asStateFlow()

    fun loadConversations() = viewModelScope.launch {
        runCatching { _conversations.value = repo.conversations() }
    }

    fun openConversation(id: String) = viewModelScope.launch {
        _conversationId.value = id
        runCatching {
            _messages.value = repo.messages(id).map { UiMessage(it.role, it.content, it.model_id) }
        }
    }

    fun newConversation() {
        _conversationId.value = null
        _messages.value = emptyList()
    }

    fun send(text: String) = viewModelScope.launch {
        if (text.isBlank() || _sending.value) return@launch
        _sending.value = true
        _messages.value = _messages.value + UiMessage("user", text)
        try {
            val r = repo.chat(_conversationId.value, text)
            _conversationId.value = r.conversation_id
            _messages.value = _messages.value + UiMessage("assistant", r.answer, r.model_id)
        } catch (e: Exception) {
            _messages.value = _messages.value + UiMessage("assistant", "⚠ Error: ${e.message}")
        }
        _sending.value = false
        loadConversations()
    }

    // ---- models / training ----
    private val _models = MutableStateFlow<List<ModelInfo>>(emptyList())
    val models = _models.asStateFlow()
    private val _status = MutableStateFlow<SystemStatus?>(null)
    val status = _status.asStateFlow()
    private val _cycles = MutableStateFlow<List<Map<String, Any>>>(emptyList())
    val cycles = _cycles.asStateFlow()
    private val _toast = MutableStateFlow<String?>(null)
    val toast = _toast.asStateFlow()

    fun clearToast() { _toast.value = null }

    fun refreshSystem() = viewModelScope.launch {
        runCatching {
            _status.value = repo.status()
            _models.value = repo.models()
        }
    }

    fun runTrainingCycle() = viewModelScope.launch {
        _toast.value = "Running training cycle…"
        runCatching { repo.runCycle() }
            .onSuccess { r ->
                _toast.value = when {
                    r.skipped != null -> "Skipped: ${r.skipped}"
                    r.status == "deployed_pending_approval" -> "Candidate ready → pending your approval"
                    r.status == "rejected" -> "Rejected (regression/safety). Strategy adapted."
                    else -> "Cycle: ${r.status ?: r.reason}"
                }
                refreshSystem()
            }
            .onFailure { _toast.value = "Error: ${it.message}" }
    }

    fun startTraining() = viewModelScope.launch {
        runCatching { repo.startTraining() }.onSuccess { _toast.value = "Continuous training started" }
        refreshSystem()
    }

    fun stopTraining() = viewModelScope.launch {
        runCatching { repo.stopTraining() }.onSuccess { _toast.value = "Training stopped" }
        refreshSystem()
    }

    fun rollback(toId: String?) = viewModelScope.launch {
        runCatching { repo.rollback(toId) }
            .onSuccess { _toast.value = "Rolled back to ${it.id.take(8)}" }
            .onFailure { _toast.value = "Rollback failed: ${it.message}" }
        refreshSystem()
    }

    // ---- approvals ----
    private val _approvals = MutableStateFlow<List<Approval>>(emptyList())
    val approvals = _approvals.asStateFlow()

    fun loadApprovals() = viewModelScope.launch {
        runCatching { _approvals.value = repo.pendingApprovals() }
    }

    fun decide(a: Approval, decision: String) = viewModelScope.launch {
        runCatching {
            repo.decide(a.id, decision)
            if (decision == "approved") repo.executeApproval(a.id)
        }.onSuccess {
            _toast.value = "Decision: $decision" + if (decision == "approved") " & applied" else ""
        }.onFailure { _toast.value = "Error: ${it.message}" }
        loadApprovals(); refreshSystem()
    }

    // ---- owner controls ----
    private val _controls = MutableStateFlow<Map<String, Any>>(emptyMap())
    val controls = _controls.asStateFlow()

    fun loadControls() = viewModelScope.launch {
        runCatching { _controls.value = repo.controls() }
    }

    fun setControl(key: String, value: Any) = viewModelScope.launch {
        runCatching { repo.setControl(key, value) }
            .onSuccess { loadControls() }
            .onFailure { _toast.value = "خطأ: ${it.message}" }
    }

    private val _emergencyStatus = MutableStateFlow<Map<String, Any>>(emptyMap())
    val emergencyStatus = _emergencyStatus.asStateFlow()
    private val _latestBundle = MutableStateFlow<StateBundleSummary?>(null)
    val latestBundle = _latestBundle.asStateFlow()
    private val _latestBundleVerification = MutableStateFlow<StateBundleVerification?>(null)
    val latestBundleVerification = _latestBundleVerification.asStateFlow()
    private val _lastEmergencyBundle = MutableStateFlow<StateBundleSummary?>(null)
    val lastEmergencyBundle = _lastEmergencyBundle.asStateFlow()
    private val _lastEmergencyBundleVerification = MutableStateFlow<StateBundleVerification?>(null)
    val lastEmergencyBundleVerification = _lastEmergencyBundleVerification.asStateFlow()

    fun loadEmergencyStatus() = viewModelScope.launch {
        runCatching { _emergencyStatus.value = repo.emergencyStatus() }
    }

    fun refreshBundles() = viewModelScope.launch {
        runCatching { _latestBundle.value = repo.latestStateBundle() }
        runCatching { _latestBundleVerification.value = repo.verifyLatestStateBundle() }
        runCatching { _lastEmergencyBundle.value = repo.lastEmergencyStateBundle() }
        runCatching { _lastEmergencyBundleVerification.value = repo.verifyLastEmergencyStateBundle() }
    }

    fun emergencyStop(reason: String = "إيقاف طارئ من تطبيق أندرويد") = viewModelScope.launch {
        _toast.value = "جاري تنفيذ الإيقاف الطارئ…"
        runCatching { repo.emergencyStop(reason, true) }
            .onSuccess {
                _toast.value = if (it.bundle != null) "تم الإيقاف الطارئ وحفظ حالة النظام" else "تم الإيقاف الطارئ"
                loadControls(); loadEmergencyStatus(); refreshSystem(); refreshBundles()
            }
            .onFailure { _toast.value = "خطأ: ${it.message}" }
    }

    fun emergencyResume() = viewModelScope.launch {
        runCatching { repo.emergencyResume() }
            .onSuccess {
                _toast.value = it.note ?: "تم رفع الإيقاف الطارئ"
                loadControls(); loadEmergencyStatus(); refreshSystem(); refreshBundles()
            }
            .onFailure { _toast.value = "خطأ: ${it.message}" }
    }

    // ---- memory ----
    private val _memories = MutableStateFlow<List<MemoryItem>>(emptyList())
    val memories = _memories.asStateFlow()

    fun loadMemories() = viewModelScope.launch {
        runCatching { _memories.value = repo.memories() }
    }

    fun importLastEmergencyBundle() = viewModelScope.launch {
        val bundle = _lastEmergencyBundle.value ?: run {
            _toast.value = "لا توجد حزمة طوارئ للاستعادة"
            return@launch
        }
        _toast.value = "جاري التحقق ثم الاستعادة…"
        runCatching { repo.importVerifiedStateBundle(bundle.id) }
            .onSuccess {
                _toast.value = it.note ?: if (it.applied) "تمت الاستعادة" else "تم التحقق"
                refreshBundles(); loadEmergencyStatus(); refreshSystem(); loadControls()
            }
            .onFailure { _toast.value = "خطأ: ${it.message}" }
    }

    fun verifyLastEmergencyBundle() = viewModelScope.launch {
        runCatching { _lastEmergencyBundleVerification.value = repo.verifyLastEmergencyStateBundle() }
            .onFailure { _toast.value = "خطأ: ${it.message}" }
    }

    fun verifyLatestBundle() = viewModelScope.launch {
        runCatching { _latestBundleVerification.value = repo.verifyLatestStateBundle() }
            .onFailure { _toast.value = "خطأ: ${it.message}" }
    }

    fun addMemory(text: String) = viewModelScope.launch {
        runCatching { repo.addMemory(text) }.onSuccess { _toast.value = "Remembered" }
        loadMemories()
    }

    fun forget(id: String) = viewModelScope.launch {
        runCatching { repo.forgetMemory(id) }
        loadMemories()
    }
}
