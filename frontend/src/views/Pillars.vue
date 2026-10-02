<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const message = ref('')

async function load() { rows.value = await api('/pillars?segment_id=1') }
onMounted(load)

const draft = ref({ position_m: 25, thickness_m: 0.5, label: '新灯柱' })
async function addPillar() {
  message.value = ''
  try {
    await api('/pillars', {
      method: 'POST',
      body: JSON.stringify({ segment_id: 1, ...draft.value }),
    })
    await load()
  } catch (e: any) { message.value = String(e?.message || e) }
}

async function savePillar(r: any) {
  message.value = ''
  try {
    await api(`/pillars/${r.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        position_m: Number(r.position_m),
        thickness_m: Number(r.thickness_m),
        label: r.label,
      }),
    })
    await load()
    // 改柱只改变当下现场；旧运行摘要不动，新确认另写新条
    message.value = '已改柱：旧运行保持冻结，去「分配带」确认新运行'
  } catch (e: any) { message.value = String(e?.message || e) }
}
</script>
<template>
  <h1>挡柱</h1>
  <p class="sub">街段障碍 · 在分配带上表现为竖直阻断块 · 改柱不会改动任何旧运行</p>
  <div class="ss-street-band" style="height:90px;min-height:90px">
    <div class="ss-street-inner" style="gap:1rem;padding:0 1rem;align-items:center">
      <div
        v-for="r in rows" :key="r.id ?? JSON.stringify(r)"
        class="ss-band-cell ss-pillar"
        :style="{ width: Math.max(r.thickness_m * 28, 36) + 'px', flex: '0 0 auto', height: '70%' }"
      >{{ r.label }} @{{ r.position_m }}m</div>
    </div>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>名称</th><th>位置(m)</th><th>厚度(m)</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td><input v-model="r.label"></td>
          <td><input v-model.number="r.position_m" type="number" step="0.1"></td>
          <td><input v-model.number="r.thickness_m" type="number" step="0.1" min="0"></td>
          <td><button class="btn" @click="savePillar(r)">钉住改动</button></td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="card">
    <strong>新增挡柱</strong>
    <div class="ss-form-row">
      <label>名称 <input v-model="draft.label"></label>
      <label>位置(m) <input v-model.number="draft.position_m" type="number" step="0.1"></label>
      <label>厚度(m) <input v-model.number="draft.thickness_m" type="number" step="0.1" min="0"></label>
      <button class="btn" @click="addPillar">添加</button>
    </div>
  </div>
  <p v-if="message" class="sub">{{ message }}</p>
</template>
