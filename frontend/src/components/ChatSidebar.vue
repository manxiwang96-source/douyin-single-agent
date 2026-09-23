<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { SidebarView, TaskProgress } from "../lib/chat";

const props = withDefaults(defineProps<{ sidebar: SidebarView; progress?: TaskProgress }>(), {
  progress: () => ({ round_id: null, phase: "idle", steps: [] }),
});

const taskBox = ref<HTMLElement | null>(null);
const pinnedToBottom = ref(true);

function onTaskScroll() {
  const el = taskBox.value;
  if (!el) return;
  pinnedToBottom.value = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
}

watch(
  () => props.progress?.steps,
  async () => {
    await nextTick();
    const el = taskBox.value;
    if (!el || !pinnedToBottom.value) return;
    el.scrollTop = el.scrollHeight;
  },
  { deep: true },
);
</script>

<template>
  <aside class="agent-sidebar">
    <section ref="taskBox" class="agent-task-progress" @scroll="onTaskScroll">
      <h3>当前任务</h3>
      <p v-if="!(progress && progress.steps.length)" class="agent-task-empty">暂无进行中的任务</p>
      <ol v-else class="agent-task-steps">
        <li
          v-for="step in progress.steps"
          :key="step.id"
          class="agent-task-step"
          :class="['is-' + step.status, { 'is-spin': step.spin }]"
        >
          <span v-if="step.spin" class="agent-task-spin" aria-hidden="true"></span>
          <span v-else-if="step.status === 'done'" class="agent-task-check" aria-hidden="true">✓</span>
          <span v-else class="agent-task-wait" aria-hidden="true"></span>
          <span class="agent-task-label">{{ step.label }}</span>
        </li>
      </ol>
    </section>
    <div class="agent-sidebar-catalog">
      <section class="agent-side-section">
        <h3>应用描述</h3>
        <p v-if="sidebar.capability_description">{{ sidebar.capability_description }}</p>
        <p v-else class="agent-side-empty">暂无描述</p>
      </section>
      <section class="agent-side-section">
        <h3>应用开发要点</h3>
        <p v-if="sidebar.development_notes">{{ sidebar.development_notes }}</p>
        <p v-else class="agent-side-empty">暂无要点</p>
      </section>
      <section class="agent-side-section">
        <h3>应用设置 / 模式</h3>
        <div class="agent-mode-switch">
          <button class="agent-mode-option is-on" type="button" disabled>{{ sidebar.agent_mode_label }}</button>
          <button class="agent-mode-option" type="button" disabled>多智能体模式</button>
        </div>
      </section>
      <section class="agent-side-section">
        <h3>知识库</h3>
        <ul v-if="sidebar.knowledge_documents.length">
          <li v-for="doc in sidebar.knowledge_documents" :key="String(doc.document_id || doc.filename || doc.title)">
            {{ doc.title || doc.filename }}
          </li>
        </ul>
        <p v-else class="agent-side-empty">暂无文档</p>
      </section>
      <section class="agent-side-section">
        <h3>工作流</h3>
        <ul v-if="sidebar.workflows.length">
          <li v-for="item in sidebar.workflows" :key="String(item.code)">{{ item.display_name }}</li>
        </ul>
        <p v-else class="agent-side-empty">暂无工作流</p>
      </section>
      <section class="agent-side-section">
        <h3>工具</h3>
        <ul v-if="sidebar.tools.length">
          <li v-for="item in sidebar.tools" :key="String(item.name)">
            <strong>{{ item.display_name }}</strong>
            <div>{{ item.user_facing_summary }}</div>
          </li>
        </ul>
        <p v-else class="agent-side-empty">暂无工具</p>
      </section>
    </div>
  </aside>
</template>
