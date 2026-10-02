<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

interface RunRow {
  id: number
  created_at: string | null
  geometry_hash: string
  summary: string
  geometry_drifted: boolean
  summary_truncated: boolean
  segment: { id: number; name: string; width_m: number }
  pillars: Array<{ id: number; position_m: number; thickness_m: number; label?: string }>
  placements: Array<{ vendor_id: number; vendor_name: string; start_m: number; end_m: number; width_m: number }>
  rejected: Array<{ vendor_id: number; vendor_name: string; width_m: number; reason: string }>
  free_spans: Array<{ start_m: number; end_m: number }>
}

const latest = ref<RunRow | null>(null)
const runs = ref<RunRow[]>([])
const selected = ref<RunRow | null>(null)
const drawerOpen = ref(false)
const busy = ref(false)
const err = ref('')
const vendors = ref<any[]>([])

const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']

async function refresh() {
  let list = await api<RunRow[]>('/allocate/runs?segment_id=1')
  if (!list.length) {
    await api('/allocate/latest?segment_id=1') // 首次：确认出第一行，而不是临时现算
    list = await api<RunRow[]>('/allocate/runs?segment_id=1')
  }
  runs.value = list
  latest.value = list[0]
  if (selected.value) {
    const stillThere = list.find(r => r.id === selected.value!.id)
    selected.value = stillThere ? await api<RunRow>(`/allocate/runs/${selected.value.id}`) : null
  }
}

async function confirmRun() {
  busy.value = true; err.value = ''
  try {
    // 新确认写新摘要、新哈希、新一行；旧行绝不被覆盖
    await api('/allocate/run?segment_id=1', { method: 'POST' })
    selected.value = null
    await refresh()
  } catch (e: any) {
    err.value = '确认失败，未留下半截运行：' + (e?.message || e)
  } finally {
    busy.value = false
  }
}

async function openRun(r: RunRow) {
  // 点开旧条：取该次冻结文本，不用当下挡柱现算
  selected.value = await api<RunRow>(`/allocate/runs/${r.id}`)
}

function shortHash(h: string) {
  return h ? h.slice(0, 15) + '…' : '—'
}

function cellsOf(run: RunRow) {
  const width = run.segment.width_m
  const out: any[] = []
  for (const p of run.pillars || []) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m / 2, w: p.thickness_m,
               label: p.label || '挡柱' })
  }
  for (const [i, p] of (run.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m, label: p.vendor_name,
               color: colors[i % colors.length] })
  }
  return out.sort((a, b) => a.start - b.start)
    .map(c => ({ ...c, pct: Math.max((c.w / width) * 100, 2) }))
}

const compareMode = computed(() =>
  !!selected.value && !!latest.value && selected.value.id !== latest.value.id)

// 非并排时，点开哪条就单独看哪条；并排时右栏恒为最新确认
const focus = computed<RunRow | null>(() =>
  selected.value && !compareMode.value ? selected.value : latest.value)

onMounted(async () => {
  vendors.value = await api('/vendors')
  await refresh()
})
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">沿街一维开间 · 挡柱为竖直阻断 · 确认时钉死当时禁入带几何哈希与逐字摘要</p>
    <div class="ss-actions">
      <button class="btn" :disabled="busy" @click="confirmRun">
        {{ busy ? '确认中…' : '确认新运行' }}
      </button>
      <button class="btn btn-ghost" @click="drawerOpen = !drawerOpen">
        运行抽屉（{{ runs.length }}）
      </button>
    </div>
    <p v-if="err" class="ss-error">{{ err }}</p>

    <div class="ss-compare" :class="{ 'ss-compare-twin': compareMode }">
      <!-- 旧条（并排时在左） -->
      <div v-if="compareMode" class="card ss-runpanel ss-runpanel-old">
        <div class="ss-panel-head">
          <strong>旧条 #{{ selected!.id }} · 冻结</strong>
          <span class="muted">{{ selected!.created_at }}</span>
        </div>
        <div class="ss-flags">
          <span v-if="selected!.geometry_drifted" class="badge badge-bad">几何已漂移</span>
          <span v-if="selected!.summary_truncated" class="badge badge-warn">摘要已截短·原样留存</span>
          <span class="badge">{{ shortHash(selected!.geometry_hash) }}</span>
        </div>
        <div class="ss-band-ruler">
          <span>0 m</span>
          <span>{{ selected!.segment.name }} · {{ selected!.segment.width_m }} m</span>
          <span>{{ selected!.segment.width_m }} m</span>
        </div>
        <div class="ss-street-band ss-band-mini">
          <div class="ss-street-inner">
            <div v-for="(c,i) in cellsOf(selected!)" :key="i"
                 class="ss-band-cell" :class="{ 'ss-pillar': c.type === 'pillar' }"
                 :style="{ width: c.pct + '%', background: c.type === 'pillar' ? undefined : c.color,
                           flex: '0 0 ' + c.pct + '%' }">{{ c.label }}</div>
          </div>
        </div>
        <pre class="ss-summary">{{ selected!.summary }}</pre>
        <button class="btn btn-ghost" @click="selected = null">收起旧条</button>
      </div>

      <!-- 当前最新确认（或单独查看某次运行） -->
      <div v-if="focus" class="card ss-runpanel">
        <div class="ss-panel-head">
          <strong>{{ compareMode ? '当前最新确认' : '冻结运行' }} #{{ focus.id }}</strong>
          <span class="muted">{{ focus.created_at }}</span>
        </div>
        <div class="ss-flags">
          <span v-if="focus.geometry_drifted" class="badge badge-bad">几何已漂移</span>
          <span v-if="focus.summary_truncated" class="badge badge-warn">摘要已截短·原样留存</span>
          <span class="badge">{{ shortHash(focus.geometry_hash) }}</span>
        </div>
        <div class="ss-band-ruler">
          <span>0 m</span>
          <span>{{ focus.segment.name }} · {{ focus.segment.width_m }} m</span>
          <span>{{ focus.segment.width_m }} m</span>
        </div>
        <div class="ss-street-band">
          <div class="ss-street-inner">
            <div v-for="(c,i) in cellsOf(focus)" :key="i"
                 class="ss-band-cell" :class="{ 'ss-pillar': c.type === 'pillar' }"
                 :style="{ width: c.pct + '%', background: c.type === 'pillar' ? undefined : c.color,
                           flex: '0 0 ' + c.pct + '%' }">{{ c.label }}</div>
          </div>
        </div>
        <table>
          <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th></tr></thead>
          <tbody>
            <tr v-for="p in focus.placements" :key="p.vendor_id">
              <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
            </tr>
          </tbody>
        </table>
        <pre class="ss-summary">{{ focus.summary }}</pre>
      </div>
    </div>

    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}</strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
      </div>
    </div>

    <!-- 运行抽屉：每一条都回库内冻结文本 -->
    <transition name="ss-slide">
      <aside v-if="drawerOpen" class="ss-drawer">
        <div class="ss-drawer-head">
          <strong>运行抽屉</strong>
          <button class="ss-x" @click="drawerOpen = false">×</button>
        </div>
        <ul class="ss-runlist">
          <li v-for="r in runs" :key="r.id"
              :class="{ active: selected?.id === r.id || (!selected && latest?.id === r.id) }"
              @click="openRun(r)">
            <div class="ss-runline">
              <span>#{{ r.id }}</span>
              <span class="muted">{{ r.created_at }}</span>
            </div>
            <div class="ss-flags">
              <span v-if="r.geometry_drifted" class="badge badge-bad">几何已漂移</span>
              <span v-if="r.summary_truncated" class="badge badge-warn">摘要截短</span>
              <span class="badge">{{ shortHash(r.geometry_hash) }}</span>
            </div>
            <pre class="ss-summary ss-summary-mini">{{ r.summary }}</pre>
          </li>
        </ul>
      </aside>
    </transition>
  </div>
</template>
