package com.homelab.commandcentre.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import com.homelab.commandcentre.ui.components.LocalStatusColorsWarning
import com.homelab.commandcentre.viewmodel.AuthViewModel

@Composable
private fun FormColumn(title: String, subtitle: String? = null, content: @Composable ColumnScope.() -> Unit) {
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp).imePadding(),
        verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.CenterVertically),
    ) {
        Text(title, style = MaterialTheme.typography.headlineSmall)
        if (subtitle != null) Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant)
        content()
    }
}

@Composable
fun ConnectScreen(vm: AuthViewModel, initial: String = "") {
    var url by remember { mutableStateOf(initial) }
    val busy by vm.busy.collectAsState()
    val error by vm.error.collectAsState()
    val warning by vm.urlWarning.collectAsState()
    FormColumn("Connect to your server", "Enter the address of your HomeLab backend, for example your server's Tailscale name or IP. \"localhost\" on a phone is the phone itself.") {
        OutlinedTextField(
            url, { url = it; vm.clearError() }, label = { Text("Server address") }, placeholder = { Text("http://100.101.102.103:8741") },
            singleLine = true, isError = error != null, modifier = Modifier.fillMaxWidth(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri),
        )
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        warning?.let { LocalStatusColorsWarning(it) }
        Button({ vm.connect(url) }, enabled = !busy && url.isNotBlank(), modifier = Modifier.fillMaxWidth()) {
            if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Text("Connect")
        }
    }
}

@Composable
fun LoginScreen(vm: AuthViewModel) {
    var user by remember { mutableStateOf("") }
    var pass by remember { mutableStateOf("") }
    val busy by vm.busy.collectAsState()
    val error by vm.error.collectAsState()
    val server by vm.baseUrl.collectAsState()
    FormColumn("Sign in", server) {
        OutlinedTextField(user, { user = it }, label = { Text("Username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(
            pass, { pass = it }, label = { Text("Password") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
            visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
        )
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button({ vm.login(user, pass) }, enabled = !busy && user.isNotBlank() && pass.isNotEmpty(), modifier = Modifier.fillMaxWidth()) {
            if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Text("Sign in")
        }
        TextButton({ vm.changeServer() }) { Text("Use a different server") }
    }
}

@Composable
fun SetupScreen(vm: AuthViewModel, tokenRequired: Boolean) {
    var user by remember { mutableStateOf("admin") }
    var pass by remember { mutableStateOf("") }
    var pass2 by remember { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    val busy by vm.busy.collectAsState()
    val error by vm.error.collectAsState()
    val mismatch = pass2.isNotEmpty() && pass != pass2
    FormColumn("Create the administrator", "First run: choose credentials for the single owner account.") {
        OutlinedTextField(user, { user = it }, label = { Text("Username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(pass, { pass = it }, label = { Text("Password (12+ characters)") }, singleLine = true, modifier = Modifier.fillMaxWidth(), visualTransformation = PasswordVisualTransformation())
        OutlinedTextField(pass2, { pass2 = it }, label = { Text("Repeat password") }, singleLine = true, isError = mismatch, supportingText = { if (mismatch) Text("Passwords do not match") }, modifier = Modifier.fillMaxWidth(), visualTransformation = PasswordVisualTransformation())
        if (tokenRequired) OutlinedTextField(token, { token = it }, label = { Text("Setup token") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
        Button({ vm.setup(user, pass, token.takeIf { it.isNotBlank() }) }, enabled = !busy && !mismatch && pass.length >= 12 && pass == pass2, modifier = Modifier.fillMaxWidth()) {
            if (busy) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp) else Text("Create account")
        }
    }
}
