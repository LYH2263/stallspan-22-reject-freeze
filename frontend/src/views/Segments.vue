<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const message = ref('')
onMounted(async () => { rows.value = await api('/segments') })

async function widen(r: any) {
  message.value = ''
  try {
    const saved = await api(`/segments/${r.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ width_m: Number(r.width_m) }),
    })
    r.width_m = saved.width_m
    // 外扩只影响当下现场；旧运行冻结的宽度与摘要不改口
    message.value = '已外扩：旧运行保持冻结，去「分配带」确认新运行'
  } catch (e: any) { message.value = String(e?.message || e) }
}
</script>
<template>
  <h1>街段</h1>
  <p class="sub">沿街可用宽度（米） · 外扩不会覆盖任何旧运行摘要</p>
  <div class="card">
    <table>
      <thead><tr><th>街段</th><th>宽度(m)</th><th>集日ID</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.name }}</td>
          <td><input v-model.number="r.width_m" type="number" step="0.5" min="0.1"></td>
          <td>{{ r.market_day_id }}</td>
          <td><button class="btn" @click="widen(r)">外扩钉住</button></td>
        </tr>
      </tbody>
    </table>
  </div>
  <p v-if="message" class="sub">{{ message }}</p>
</template>
