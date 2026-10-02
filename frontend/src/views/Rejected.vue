<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
import RunDrawer from '../components/RunDrawer.vue'

const run = ref<any | null>(null)
const drawer = ref<InstanceType<typeof RunDrawer> | null>(null)

async function loadLatest() {
  try { run.value = await api('/allocate/latest?segment_id=1') }
  catch { run.value = null }
}
async function openRun(id: number) {
  if (id === run.value?.id) return
  run.value = await api(`/allocate/runs/${id}?segment_id=1`)
}
onMounted(loadLatest)
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">无法在连续空档内安置且不跨越挡柱的摊位 · 旁注与运行抽屉、详情逐字相同</p>
  <div class="card" v-if="run">
    <div style="display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;margin-bottom:.4rem">
      <strong>运行 #{{ run.id }} 旁注（逐字）</strong>
      <span v-if="run.geometry_drift" class="badge badge-warn">几何已漂移</span>
      <span v-if="run.summary_dirty" class="badge badge-bad">摘要已截短</span>
      <span v-if="!run.geometry_drift && !run.summary_dirty" class="badge badge-ok">固化一致</span>
    </div>
    <p class="ss-rej-summary">{{ run.summary }}</p>
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
      <tbody>
        <tr v-for="r in run.rejected" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!run.rejected?.length" class="muted">全部放下</p>
  </div>
  <div class="card" v-else><p class="muted">尚无已确认运行，请先到分配带确认一次。</p></div>
  <RunDrawer ref="drawer" :current-id="run?.id ?? null" @select="openRun" />
</template>
<style scoped>
.ss-rej-summary {
  margin: 0 0 0.6rem; padding: 0.35rem 0.6rem;
  background: rgba(255,255,255,0.4); border-left: 3px solid var(--ss-accent);
  font-size: 0.85rem; color: var(--ss-curb); word-break: break-all;
}
</style>
