package com.homelab.commandcentre.core

import com.homelab.commandcentre.core.data.*
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.flow.take
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import java.time.Instant
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertTrue

@OptIn(ExperimentalCoroutinesApi::class)
class PollingTest {
    private val t0 = Instant.parse("2026-01-01T00:00:00Z")

    @Test fun emitsLoadingThenContent() = runTest {
        val states = pollingFlow(intervalMs = { 1000 }, now = { t0 }) { ApiResult.Success(1) }.take(2).toList()
        assertEquals(Loadable.Loading, states[0])
        assertEquals(Loadable.Content(1, t0), states[1])
    }

    @Test fun firstFailureIsFailedNotEmptyContent() = runTest {
        val states = pollingFlow({ 1000 }) { ApiResult.Failure(ApiFailure.Offline()) }.take(2).toList()
        assertIs<Loadable.Failed>(states[1])
        assertTrue(states[1].isDisconnected)
    }

    @Test fun failureAfterSuccessKeepsDataButFlagsItAsStale() = runTest {
        var n = 0
        val out = mutableListOf<Loadable<Int>>()
        val job = launch { pollingFlow({ 1000 }, now = { t0 }) { if (n++ == 0) ApiResult.Success(42) else ApiResult.Failure(ApiFailure.Offline()) }.take(3).toList(out) }
        advanceTimeBy(1500); runCurrent(); job.join()
        val last = out.last() as Loadable.Content
        assertEquals(42, last.data)                      // last known value retained ...
        assertEquals(t0, last.updatedAt)                 // ... with its original timestamp ...
        assertIs<ApiFailure.Offline>(last.refreshError)  // ... explicitly marked as failing
        assertTrue(last.isDisconnected)
    }

    @Test fun recoversAndClearsTheErrorFlag() = runTest {
        var n = 0
        val out = mutableListOf<Loadable<Int>>()
        val job = launch { pollingFlow({ 1000 }, now = { t0 }) { when (n++) { 0 -> ApiResult.Success(1); 1 -> ApiResult.Failure(ApiFailure.Offline()); else -> ApiResult.Success(3) } }.take(4).toList(out) }
        advanceTimeBy(2500); runCurrent(); job.join()
        assertEquals(Loadable.Content(3, t0), out.last())
    }

    @Test fun pollsOnTheConfiguredIntervalAndReadsItEachCycle() = runTest {
        var calls = 0; var interval = 1000L
        val job = launch { pollingFlow({ interval }) { calls++; ApiResult.Success(calls) }.collect { } }
        runCurrent(); assertEquals(1, calls)
        advanceTimeBy(999); runCurrent(); assertEquals(1, calls)
        advanceTimeBy(2); runCurrent(); assertEquals(2, calls)
        interval = 5000
        advanceTimeBy(1000); runCurrent(); assertEquals(3, calls)   // old interval elapsed once more
        advanceTimeBy(4000); runCurrent(); assertEquals(3, calls)   // new interval not reached yet
        advanceTimeBy(1100); runCurrent(); assertEquals(4, calls)
        job.cancel()
    }

    @Test fun pullToRefreshTriggersImmediateFetch() = runTest {
        var calls = 0
        val refresh = MutableSharedFlow<Unit>()
        val job = launch { pollingFlow({ 60_000 }, refresh) { calls++; ApiResult.Success(calls) }.collect { } }
        runCurrent(); assertEquals(1, calls)
        refresh.emit(Unit); runCurrent(); assertEquals(2, calls)
        job.cancel()
    }

    @Test fun stopsPollingWhenSessionIsDead() = runTest {
        var calls = 0
        val out = pollingFlow({ 1000 }) { calls++; ApiResult.Failure(ApiFailure.Unauthorized()) }.toList()
        assertEquals(1, calls)
        assertIs<ApiFailure.Unauthorized>((out.last() as Loadable.Failed).failure)
    }
}
