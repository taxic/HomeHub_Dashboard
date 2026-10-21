package com.homelab.commandcentre.core.domain

import com.homelab.commandcentre.core.api.ContainerOut
import com.homelab.commandcentre.core.data.ApiResult
import com.homelab.commandcentre.core.data.ContainerAction
import com.homelab.commandcentre.core.data.HomeLabRepository
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

sealed interface ActionState {
    data object Idle : ActionState
    data class Confirming(val container: ContainerOut, val action: ContainerAction) : ActionState
    data class Running(val container: ContainerOut, val action: ContainerAction) : ActionState
    data class Succeeded(val container: ContainerOut, val action: ContainerAction, val message: String) : ActionState
    data class Failed(val container: ContainerOut, val action: ContainerAction, val message: String) : ActionState
}

/**
 * Confirm -> progress -> result flow for start/stop/restart. A command can only be sent from the
 * [ActionState.Confirming] state, so nothing is ever executed without an explicit confirmation,
 * and a second tap while [ActionState.Running] cannot send a duplicate request.
 */
class ContainerActionController(private val repo: HomeLabRepository) {
    private val _state = MutableStateFlow<ActionState>(ActionState.Idle)
    val state: StateFlow<ActionState> = _state.asStateFlow()

    fun request(container: ContainerOut, action: ContainerAction) {
        if (_state.value is ActionState.Running) return
        if (action !in ContainerPolicy.available(container)) return // not offered => not sendable
        _state.value = ActionState.Confirming(container, action)
    }

    /** Returns true when the action finished (successfully or not) so callers can refresh lists. */
    suspend fun confirm(): Boolean {
        val s = _state.value as? ActionState.Confirming ?: return false
        _state.value = ActionState.Running(s.container, s.action)
        _state.value = when (val r = repo.containerAction(s.container.id, s.action)) {
            is ApiResult.Success -> ActionState.Succeeded(s.container, s.action, r.value.message)
            is ApiResult.Failure -> ActionState.Failed(s.container, s.action, r.failure.message)
        }
        return true
    }

    fun dismiss() {
        if (_state.value !is ActionState.Running) _state.value = ActionState.Idle
    }
}
