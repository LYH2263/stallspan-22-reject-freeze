<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import RunDrawer from '../components/RunDrawer.vue'

const vendors = ref<any[]>([])
const latest = ref<any | null>(null)
const selected = ref<any | null>(null)
const drawer = ref<InstanceType<typeof RunDrawer> | null>(null)
const notFound = ref(false)
const confirming = ref(false)

async function loadLatest() {
  try {
    latest.value = await api('/allocate/latest?segment_id=1')
    notFound.value = false
  } catch (e: any) {
    latest.value = null
    notFound.value = true
  }
  selected.value = latest.value
}
async function confirmRun() {
  confirming.value = true
  try {
    latest.value = await api('/allocate/run?segment_id=1', { method: 'POST' })
    selected.value = latest.value
    notFound.value = false
    await drawer.value?.load()
  } finally {
    confirming.value = false
  }
}
async function openRun(id: number) {
  if (id === latest.value?.id) { selected.value = latest.value; return }
  selected.value = await api(`/allocate/runs/${id}?segment_id=1`)
}
onMounted(async () => {
  vendors.value = await api('/vendors')
  await loadLatest()
})

const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
function cellsOf(run: any) {
  if (!run) return []
  const width = run.segment.width_m
  const out: any[] = []
  for (const p of run.pillars || []) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m/2, w: p.thickness_m, label: p.label || '挡柱' })
  }
  for (const [i, p] of (run.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m, label: p.vendor_name, color: colors[i % colors.length] })
  }
  return out.sort((a,b) => a.start - b.start).map(c => ({ ...c, pct: Math.max((c.w / width) * 100, 2) }))
}
const comparing = computed(() =>
  selected.value && latest.value && selected.value.id !== latest.value.id ? selected.value : null)
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">历史运行为只读快照 · 改柱/外扩后旧条不改口，只亮「几何已漂移」</p>
    <div>
      <button class="btn" :disabled="confirming" @click="confirmRun">
        {{ confirming ? '固化中…' : '确认新运行（钉住此刻几何）' }}
      </button>
    </div>

    <div v-if="notFound" class="card" style="margin-top:0.5rem">
      <span class="muted">尚无已确认运行——点击上方按钮确认第一次运行。</span>
    </div>

    <div v-if="selected" class="ss-compare" :class="{ 'is-split': comparing }">
      <div class="ss-run-panel">
        <div class="ss-run-head">
          <strong>{{ comparing ? '历史运行 #' + selected.id : '最新运行 #' + latest?.id }}</strong>
          <span class="badge badge-warn" v-if="selected.geometry_drift">几何已漂移</span>
          <span class="badge badge-bad" v-if="selected.summary_dirty">摘要已截短</span>
          <span class="badge badge-ok" v-if="!selected.geometry_drift && !selected.summary_dirty">固化一致</span>
        </div>
        <p class="ss-summary-note">旁注（逐字）：{{ selected.summary }}</p>
        <div class="ss-band-ruler">
          <span>0 m</span>
          <span>{{ selected.segment.name }} · {{ selected.segment.width_m }} m · 哈希 {{ selected.geom_hash }}</span>
          <span>{{ selected.segment.width_m }} m</span>
        </div>
        <div class="ss-street-band">
          <div class="ss-street-inner">
            <div
              v-for="(c,i) in cellsOf(selected)" :key="i"
              class="ss-band-cell"
              :class="{ 'ss-pillar': c.type === 'pillar' }"
              :style="{ width: c.pct + '%', background: c.type === 'pillar' ? undefined : c.color, flex: '0 0 ' + c.pct + '%' }"
            >{{ c.label }}</div>
          </div>
        </div>
      </div>

      <div v-if="comparing" class="ss-run-panel">
        <div class="ss-run-head">
          <strong>当前最新 #{{ latest.id }}</strong>
          <span class="badge badge-warn" v-if="latest.geometry_drift">几何已漂移</span>
          <span class="badge badge-ok" v-else>固化一致</span>
        </div>
        <p class="ss-summary-note">旁注（逐字）：{{ latest.summary }}</p>
        <div class="ss-band-ruler">
          <span>0 m</span>
          <span>{{ latest.segment.name }} · {{ latest.segment.width_m }} m · 哈希 {{ latest.geom_hash }}</span>
          <span>{{ latest.segment.width_m }} m</span>
        </div>
        <div class="ss-street-band">
          <div class="ss-street-inner">
            <div
              v-for="(c,i) in cellsOf(latest)" :key="i"
              class="ss-band-cell"
              :class="{ 'ss-pillar': c.type === 'pillar' }"
              :style="{ width: c.pct + '%', background: c.type === 'pillar' ? undefined : c.color, flex: '0 0 ' + c.pct + '%' }"
            >{{ c.label }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
      </div>
    </div>

    <div class="card" v-if="selected">
      <table>
        <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
        <tbody>
          <tr v-for="p in selected.placements" :key="p.vendor_id">
            <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <RunDrawer ref="drawer" :current-id="selected?.id ?? null" @select="openRun" />
  </div>
</template>
<style scoped>
.ss-compare { display: block; margin-top: 0.5rem; }
.ss-compare.is-split { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; }
.ss-run-panel { min-width: 0; }
.ss-run-head { display: flex; align-items: center; gap: 0.4rem; font-size: 0.82rem; }
.ss-summary-note {
  margin: 0.35rem 0; font-size: 0.8rem; color: var(--ss-curb);
  background: rgba(255,255,255,0.35); border-left: 3px solid var(--ss-accent);
  padding: 0.3rem 0.55rem; word-break: break-all;
}
</style>
