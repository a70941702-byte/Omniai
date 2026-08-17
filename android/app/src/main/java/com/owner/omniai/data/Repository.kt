package com.owner.omniai.data

import android.content.Context
import android.provider.Settings
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import okhttp3.OkHttpClient
import okhttp3.Interceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

class Repository(private val context:Context) {
 private val prefs = EncryptedSharedPreferences.create(context,"omniai_secure",MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build(),EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM)
 var baseUrl:String
  get()=prefs.getString("base_url","https://127.0.0.1:8000/api/v1/")!!
  set(v){prefs.edit().putString("base_url",v).apply()}
 private val api:OmniApi get(){
  val client=OkHttpClient.Builder().connectTimeout(30,TimeUnit.SECONDS).readTimeout(300,TimeUnit.SECONDS).writeTimeout(60,TimeUnit.SECONDS).addInterceptor(Interceptor { chain ->
   val token=prefs.getString("session",null); val req=chain.request().newBuilder(); if(token!=null) req.header("Authorization","Bearer $token"); chain.proceed(req.build())
  }).build()
  return Retrofit.Builder().baseUrl(if(baseUrl.endsWith('/')) baseUrl else "$baseUrl/").client(client).addConverterFactory(GsonConverterFactory.create()).build().create(OmniApi::class.java)
 }
 val isLoggedIn:Boolean get()=prefs.getString("session",null)!=null
 suspend fun login(ownerToken:String):Boolean { val r=api.login(LoginRequest(ownerToken, Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID))); if(!r.ok)return false; prefs.edit().putString("session",r.token).apply(); return true }
 suspend fun logout(){ runCatching{api.logout("Bearer ${prefs.getString("session","")}")}; prefs.edit().remove("session").apply() }
 suspend fun chat(id:String?,text:String)=api.chat(ChatRequest(id,text,system_prompt="أنت OmniAI — مساعد شخصي. أجب دائماً بنفس لغة المستخدم، وإذا كتب بالعربية فأجب بالعربية الفصحى الواضحة."))
 suspend fun conversations()=api.conversations(); suspend fun messages(id:String)=api.messages(id); suspend fun models()=api.models(); suspend fun status()=api.status()
 suspend fun pendingApprovals()=api.approvals("pending"); suspend fun decide(id:String,d:String)=api.decide(id,DecisionBody(d,"قرار المالك من تطبيق أندرويد")); suspend fun executeApproval(id:String)=api.execute(id)
 suspend fun runCycle()=api.trainingCycle(); suspend fun startTraining()=api.startTraining(); suspend fun stopTraining()=api.stopTraining(); suspend fun rollback(id:String?)=api.rollback(id)
 suspend fun controls()=api.controls(); suspend fun setControl(k:String,v:Any)=api.setControls(ControlsBody(mapOf(k to v)))
 suspend fun memories()=api.memories(); suspend fun addMemory(t:String)=api.addMemory(MemoryBody(t)); suspend fun forgetMemory(id:String)=api.forget(id)
 suspend fun improveAnalyze()=api.improveAnalyze(); suspend fun improvePropose()=api.improvePropose()
}
