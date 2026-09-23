<script setup lang="ts">
import type { SidebarView } from "../lib/chat";

defineProps<{ sidebar: SidebarView }>();
</script>

<template>
  <aside class="agent-sidebar">
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
  </aside>
</template>
