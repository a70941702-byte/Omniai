package com.owner.omniai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.owner.omniai.ui.*
import com.owner.omniai.viewmodel.MainViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(
                colorScheme = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()
            ) {
                val vm: MainViewModel = viewModel()
                val loggedIn by vm.loggedIn.collectAsState()
                val nav = rememberNavController()

                if (!loggedIn) {
                    LoginScreen(vm)
                } else {
                    NavHost(nav, startDestination = "chat") {
                        composable("chat") { ChatScreen(vm) { route -> nav.navigate(route) } }
                        composable("system") { SystemScreen(vm) }
                        composable("approvals") { ApprovalsScreen(vm) }
                        composable("controls") { ControlsScreen(vm) }
                    }
                }
            }
        }
    }
}
