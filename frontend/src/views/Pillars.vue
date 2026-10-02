<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const form = ref({ position_m: 15, thickness_m: 0.4, label: '新增灯柱' })
const busy = ref(false)
const err = ref('')
async function load() { rows.value = await api('/pillars') }
async function addPillar() {
  busy.value = true; err.value = ''
  try {
    await api('/pillars', { method: 'POST', body: JSON.stringify({ segment_id: 1, ...form.value }) })
    await load()
  } catch (e: any) { err.value = String(e.message || e) }
  finally { busy.value = false }
}
async function removePillar(id: number) {
  await api(`/pillars/${id}`, { method: 'DELETE' })
  await load()
}
onMounted(load)
</script>
<template>
  <h1>挡柱</h1>
  <p class="sub">改柱只影响此后确认的运行；历史运行钉存的几何与摘要不改写，只亮「几何已漂移」</p>
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
    <strong>新增挡柱（改柱）</strong>
    <div style="display:flex;gap:.5rem;align-items:end;flex-wrap:wrap;margin-top:.5rem">
      <label>位置(m)<br><input v-model.number="form.position_m" type="number" step="0.1" min="0"></label>
      <label>厚度(m)<br><input v-model.number="form.thickness_m" type="number" step="0.1" min="0.1"></label>
      <label>名称<br><input v-model="form.label" type="text"></label>
      <button class="btn" :disabled="busy" @click="addPillar">钉下挡柱</button>
    </div>
    <p v-if="err" class="badge badge-bad" style="margin-top:.4rem">{{ err }}</p>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>名称</th><th>位置(m)</th><th>厚度(m)</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.label }}</td><td>{{ r.position_m }}</td><td>{{ r.thickness_m }}</td>
          <td><button class="btn" style="padding:.2rem .6rem" @click="removePillar(r.id)">移除</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
