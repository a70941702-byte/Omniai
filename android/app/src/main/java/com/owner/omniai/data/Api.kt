package com.owner.omniai.data

import retrofit2.http.*

data class LoginRequest(val token:String,val device_id:String?=null)
data class LoginResponse(val ok:Boolean, val token:String, val expires_in:Long?=null)
data class ChatRequest(val conversation_id:String?=null,val text:String,val system_prompt:String?=null,val temperature:Double=.7,val top_p:Double=.9,val max_tokens:Int=512)
data class ChatResponse(val conversation_id:String,val answer:String,val intent:String?,val tool:String?,val model_id:String,val latency_s:Double?)
data class Conversation(val id:String,val title:String,val created_at:Double,val updated_at:Double)
data class Message(val id:String,val conversation_id:String,val role:String,val content:String,val model_id:String?,val created_at:Double)
data class ModelInfo(val id:String,val version:Int,val parent_id:String?,val status:String,val model_type:String?,val metrics:Any?,val created_at:Double)
data class Approval(val id:String,val kind:String,val payload:Map<String,Any?>,val status:String,val decision_note:String?,val created_at:Double)
data class MemoryItem(val id:String,val kind:String,val text:String,val importance:Double,val pinned:Boolean,val created_at:Double)
data class SystemStatus(
    val current_model:String?,
    val current_model_version:Int?,
    val training_thread_alive:Boolean,
    val controls:Map<String,Any>,
    val counts:Map<String,Any>,
    val schema:Map<String,Any>?=null,
    val runtime_loaded:Boolean?=null,
    val emergency:Map<String,Any>?=null
)
data class TrainResponse(val status:String?=null,val skipped:String?=null,val reason:String?=null)
data class EmptyBody(val noop:String?=null)
data class DecisionBody(val decision:String,val note:String?=null)
data class MemoryBody(val text:String,val kind:String="semantic")
data class ControlsBody(val values:Map<String,Any>)
data class OkResponse(val ok:Boolean?=null)
data class StateBundleSummary(val id:String,val path:String?=null,val manifest_path:String?=null,val note:String?=null,val schema_version:Int?=null,val status:String?=null,val created_at:Double?=null)
data class StateBundleVerification(val id:String,val ok:Boolean,val problems:List<String> = emptyList(),val schema:Map<String,Any>?=null,val audit_chain:Map<String,Any>?=null,val counts:Map<String,Any>?=null,val path:String?=null)
data class StateBundleImportResponse(val importable:Boolean,val applied:Boolean,val id:String,val note:String?=null,val schema:Map<String,Any>?=null,val counts:Map<String,Any>?=null)
data class EmergencyStopResponse(val stopped:Boolean?=null,val kill_switch:Boolean?=null,val reason:String?=null,val resumed:Boolean?=null,val note:String?=null,val bundle:StateBundleSummary?=null)

interface OmniApi {
 @POST("auth/login") suspend fun login(@Body body:LoginRequest):LoginResponse
 @POST("auth/logout") suspend fun logout(@Header("Authorization") auth:String):OkResponse
 @POST("chat") suspend fun chat(@Body body:ChatRequest):ChatResponse
 @GET("conversations") suspend fun conversations():List<Conversation>
 @GET("conversations/{id}/messages") suspend fun messages(@Path("id") id:String):List<Message>
 @GET("models") suspend fun models():List<ModelInfo>
 @GET("status") suspend fun status():SystemStatus
 @GET("approvals") suspend fun approvals(@Query("status") status:String?=null):List<Approval>
 @POST("approvals/{id}/decide") suspend fun decide(@Path("id") id:String,@Body body:DecisionBody):Approval
 @POST("approvals/{id}/execute") suspend fun execute(@Path("id") id:String):OkResponse
 @POST("training/cycle") suspend fun trainingCycle(@Body body:EmptyBody = EmptyBody()):TrainResponse
 @POST("training/start") suspend fun startTraining():OkResponse
 @POST("training/stop") suspend fun stopTraining():OkResponse
 @POST("models/rollback") suspend fun rollback(@Query("to_model_id") id:String?):ModelInfo
 @GET("controls") suspend fun controls():Map<String,Any>
 @POST("controls") suspend fun setControls(@Body body:ControlsBody):Map<String,Any>
 @GET("memory") suspend fun memories():List<MemoryItem>
 @POST("memory") suspend fun addMemory(@Body body:MemoryBody):OkResponse
 @DELETE("memory/{id}") suspend fun forget(@Path("id") id:String):OkResponse
 @GET("improve/analyze") suspend fun improveAnalyze():Map<String,Any>
 @POST("improve/propose") suspend fun improvePropose():Map<String,Any>
 @POST("emergency/stop") suspend fun emergencyStop(@Query("reason") reason:String="Owner emergency stop",@Query("export_bundle") exportBundle:Boolean=true):EmergencyStopResponse
 @POST("emergency/resume") suspend fun emergencyResume():EmergencyStopResponse
 @GET("emergency/status") suspend fun emergencyStatus():Map<String,Any>
 @GET("state-bundles") suspend fun stateBundles():List<StateBundleSummary>
 @GET("state-bundles/latest") suspend fun latestStateBundle():StateBundleSummary
 @GET("state-bundles/latest/verify") suspend fun verifyLatestStateBundle():StateBundleVerification
 @GET("state-bundles/last-emergency") suspend fun lastEmergencyStateBundle():StateBundleSummary
 @GET("state-bundles/last-emergency/verify") suspend fun verifyLastEmergencyStateBundle():StateBundleVerification
 @POST("state-bundles/{id}/verify-and-import") suspend fun importVerifiedStateBundle(@Path("id") id:String):StateBundleImportResponse
}
