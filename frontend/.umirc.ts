import { defineConfig } from '@umijs/max';

export default defineConfig({
  antd: {},
  access: {},
  model: {},
  initialState: {},
  request: {},
  layout: {
    title: '流程图工具箱',
  },
  routes: [
    {
      path: '/401',
      layout: false,
      component: './401',
    },
    {
      path: '/',
      redirect: '/flowchart/workbench',
    },
    {
      name: '流程图工作台',
      path: '/flowchart/workbench',
      component: './FlowchartWorkbench',
    },
    {
      name: '权限演示',
      path: '/access',
      component: './Access',
      hideInMenu: true,
    },
    {
      name: 'CRUD 示例',
      path: '/table',
      component: './Table',
      hideInMenu: true,
    },
    {
      path: '*',
      layout: false,
      component: './404',
    },
  ],
  npmClient: 'pnpm',
  utoopack: {},
  // setup.sh 会替换 20105、10105
  proxy: {
    '/api': {
      target: 'http://localhost:10105/',
      changeOrigin: true,
    },
  },
});
