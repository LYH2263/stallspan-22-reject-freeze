<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const rows = ref<any[]>([])
const summary = ref('')
const geomHash = ref('')
const drifted = ref(false)
const truncated = ref(false)
const runId = ref<number | null>(null)

onMounted(async () => {
  const data = await api<any>('/allocate/latest?segment_id=1')
  rows.value = data.rejected || []
  // 旁注必须逐字回库内冻结文本，绝不按当下挡柱另算一份
  summary.value = data.summary || ''
  geomHash.value = data.geometry_hash || ''
  drifted.value = !!data.geometry_drifted
  truncated.value = !!data.summary_truncated
  runId.value = data.id
})
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">无法在连续空档内安置且不跨越挡柱的摊位 · 旁注为该次确认钉死的逐字摘要</p>
  <div class="ss-rejected-grid">
    <div class="card">
      <table>
        <thead><tr><th>摊主</th><th>需求宽度</th><th>原因</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.vendor_id">
            <td>{{ r.vendor_name }}</td><td>{{ r.width_m }}</td><td>{{ r.reason }}</td>
          </tr>
        </tbody>
      </table>
      <p v-if="!rows.length" class="muted">全部放下</p>
    </div>
    <aside class="card ss-margin-note">
      <div class="ss-panel-head">
        <strong>旁注 · 运行 #{{ runId }}</strong>
      </div>
      <div class="ss-flags">
        <span v-if="drifted" class="badge badge-bad">几何已漂移</span>
        <span v-if="truncated" class="badge badge-warn">摘要已截短·原样留存</span>
      </div>
      <!-- 逐字文本：多口分叉即废；截短也照显，不回写 -->
      <pre class="ss-summary">{{ summary }}</pre>
    </aside>
  </div>
</template>
