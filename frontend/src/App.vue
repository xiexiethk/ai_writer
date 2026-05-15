<template>
  <n-config-provider :theme="isDark ? darkTheme : null" :theme-overrides="themeOverrides">
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { darkTheme } from 'naive-ui'
import type { GlobalThemeOverrides } from 'naive-ui'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const isDark = computed(() => appStore.isDark)

const themeOverrides = computed<GlobalThemeOverrides>(() => {
  if (isDark.value) {
    return {
      common: {
        fontFamily:
          '"Avenir Next", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
        fontFamilyMono:
          '"SFMono-Regular", "JetBrains Mono", "Fira Code", "Roboto Mono", monospace',
        primaryColor: '#dd8459',
        primaryColorHover: '#e69970',
        primaryColorPressed: '#c56d43',
        successColor: '#6da380',
        warningColor: '#c59453',
        errorColor: '#c46f64',
        infoColor: '#a79884',
        bodyColor: '#18130f',
        cardColor: '#241c16',
        modalColor: '#241c16',
        popoverColor: '#2a211a',
        tableColor: '#201914',
        borderColor: '#493c31',
        dividerColor: '#3c3027',
        borderRadius: '18px',
        borderRadiusSmall: '12px',
        textColorBase: '#f3ece2',
        textColor1: '#f3ece2',
        textColor2: '#ded2c4',
        textColor3: '#b9ab98',
        placeholderColor: '#91826f',
        hoverColor: 'rgba(255, 248, 240, 0.05)',
      },
      Layout: {
        color: '#18130f',
        siderColor: '#1d1611',
        headerColor: 'rgba(28, 22, 17, 0.78)',
        footerColor: '#18130f',
      },
      Card: {
        color: '#241c16',
        colorModal: '#241c16',
        borderColor: '#493c31',
      },
      Button: {
        textColorPrimary: '#fff8f2',
        textColorHoverPrimary: '#fff8f2',
        textColorPressedPrimary: '#fff8f2',
        colorPrimary: '#dd8459',
        colorHoverPrimary: '#e69970',
        colorPressedPrimary: '#c56d43',
        colorPrimaryFocus: '#e69970',
        borderPrimary: '1px solid #dd8459',
        borderHoverPrimary: '1px solid #e69970',
        borderPressedPrimary: '1px solid #c56d43',
        borderRadiusTiny: '12px',
        borderRadiusSmall: '14px',
        borderRadiusMedium: '16px',
      },
      Input: {
        color: 'rgba(255, 250, 244, 0.03)',
        colorFocus: 'rgba(255, 250, 244, 0.05)',
        border: '1px solid #493c31',
        borderHover: '1px solid #6e5a47',
        borderFocus: '1px solid #dd8459',
        boxShadowFocus: '0 0 0 3px rgba(221, 132, 89, 0.16)',
      },
      Modal: {
        color: '#241c16',
      },
      Menu: {
        color: '#1d1611',
        itemColorActive: 'rgba(221, 132, 89, 0.14)',
        itemColorActiveHover: 'rgba(221, 132, 89, 0.2)',
        itemColorHover: 'rgba(255, 250, 244, 0.05)',
        itemTextColor: '#cdbfac',
        itemTextColorHover: '#f3ece2',
        itemTextColorActive: '#f3ece2',
        itemIconColor: '#a99887',
        itemIconColorHover: '#f3ece2',
        itemIconColorActive: '#f3ece2',
        arrowColor: '#a99887',
      },
      Tag: {
        borderRadius: '999px',
      },
    }
  }

  return {
    common: {
      fontFamily:
        '"Avenir Next", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
      fontFamilyMono:
        '"SFMono-Regular", "JetBrains Mono", "Fira Code", "Roboto Mono", monospace',
      primaryColor: '#c96f45',
      primaryColorHover: '#d6825d',
      primaryColorPressed: '#b75c34',
      successColor: '#537d62',
      warningColor: '#a36d39',
      errorColor: '#b95f4a',
      infoColor: '#8a7964',
      bodyColor: '#f3ede3',
      cardColor: '#faf6ef',
      modalColor: '#faf6ef',
      popoverColor: '#fffaf2',
      tableColor: '#fffaf2',
      borderColor: '#d8ccba',
      dividerColor: '#ddd2c2',
      borderRadius: '18px',
      borderRadiusSmall: '12px',
      textColorBase: '#201b16',
      textColor1: '#201b16',
      textColor2: '#4c4237',
      textColor3: '#76695c',
      placeholderColor: '#9b8d7f',
      hoverColor: 'rgba(201, 111, 69, 0.06)',
    },
    Layout: {
      color: '#f3ede3',
      siderColor: '#efe6d8',
      headerColor: 'rgba(250, 246, 239, 0.86)',
      footerColor: '#f3ede3',
    },
    Card: {
      color: '#faf6ef',
      colorModal: '#faf6ef',
      borderColor: '#d8ccba',
    },
    Button: {
      textColorPrimary: '#fffaf4',
      textColorHoverPrimary: '#fffaf4',
      textColorPressedPrimary: '#fffaf4',
      colorPrimary: '#c96f45',
      colorHoverPrimary: '#d6825d',
      colorPressedPrimary: '#b75c34',
      colorPrimaryFocus: '#d6825d',
      borderPrimary: '1px solid #c96f45',
      borderHoverPrimary: '1px solid #d6825d',
      borderPressedPrimary: '1px solid #b75c34',
      borderRadiusTiny: '12px',
      borderRadiusSmall: '14px',
      borderRadiusMedium: '16px',
    },
    Input: {
      color: 'rgba(255, 250, 242, 0.9)',
      colorFocus: '#fffdf9',
      border: '1px solid #d8ccba',
      borderHover: '1px solid #bea98d',
      borderFocus: '1px solid #c96f45',
      boxShadowFocus: '0 0 0 3px rgba(201, 111, 69, 0.14)',
    },
    Modal: {
      color: '#faf6ef',
    },
    Menu: {
      color: '#efe6d8',
      itemColorActive: 'rgba(201, 111, 69, 0.12)',
      itemColorActiveHover: 'rgba(201, 111, 69, 0.16)',
      itemColorHover: 'rgba(201, 111, 69, 0.06)',
      itemTextColor: '#4c4237',
      itemTextColorHover: '#201b16',
      itemTextColorActive: '#201b16',
      itemIconColor: '#76695c',
      itemIconColorHover: '#201b16',
      itemIconColorActive: '#201b16',
      arrowColor: '#76695c',
    },
    Tag: {
      borderRadius: '999px',
    },
  }
})
</script>

<style>
:root {
  color-scheme: light;
  --aw-font-ui: "Avenir Next", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei",
    sans-serif;
  --aw-font-display: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
  --aw-bg: #f3ede3;
  --aw-shell: rgba(250, 246, 239, 0.82);
  --aw-paper: #faf6ef;
  --aw-paper-strong: #fffaf3;
  --aw-paper-soft: #efe6d8;
  --aw-border: #d8ccba;
  --aw-border-strong: #bea98d;
  --aw-text: #201b16;
  --aw-text-soft: #4c4237;
  --aw-text-muted: #76695c;
  --aw-accent: #c96f45;
  --aw-accent-strong: #b75c34;
  --aw-accent-soft: rgba(201, 111, 69, 0.1);
  --aw-success-soft: rgba(83, 125, 98, 0.12);
  --aw-shadow: 0 22px 70px rgba(94, 73, 49, 0.12);
}

html.dark {
  color-scheme: dark;
  --aw-bg: #18130f;
  --aw-shell: rgba(29, 22, 17, 0.82);
  --aw-paper: #241c16;
  --aw-paper-strong: #2b221b;
  --aw-paper-soft: #1d1611;
  --aw-border: #493c31;
  --aw-border-strong: #6e5a47;
  --aw-text: #f3ece2;
  --aw-text-soft: #ded2c4;
  --aw-text-muted: #b9ab98;
  --aw-accent: #dd8459;
  --aw-accent-strong: #c56d43;
  --aw-accent-soft: rgba(221, 132, 89, 0.14);
  --aw-success-soft: rgba(109, 163, 128, 0.14);
  --aw-shadow: 0 28px 90px rgba(0, 0, 0, 0.32);
}

html,
body,
#app {
  height: 100%;
  margin: 0;
  padding: 0;
  font-family: var(--aw-font-ui);
}

html {
  background: var(--aw-bg);
}

body {
  background: var(--aw-bg);
  color: var(--aw-text);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

body::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    linear-gradient(rgba(124, 102, 79, 0.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(124, 102, 79, 0.035) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: radial-gradient(circle at center, rgba(0, 0, 0, 0.26), transparent 82%);
}

#app {
  position: relative;
}

h1,
h2,
h3,
h4,
h5,
h6 {
  font-family: var(--aw-font-display);
  letter-spacing: -0.02em;
}

a {
  color: var(--aw-accent);
  text-decoration: none;
}

* {
  box-sizing: border-box;
}

::selection {
  background: rgba(201, 111, 69, 0.22);
}

::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

::-webkit-scrollbar-thumb {
  background: rgba(127, 106, 84, 0.34);
  border-radius: 999px;
}

::-webkit-scrollbar-track {
  background: transparent;
}
</style>
