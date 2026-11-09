const {defineConfig}=require('@playwright/test');
const path=require('node:path');
module.exports=defineConfig({
  testDir: '.', testMatch: '*.spec.cjs', timeout: 30000, retries: 0, workers: 2,
  reporter: [['list']],
  use: {baseURL:'http://127.0.0.1:4173',browserName:'chromium',reducedMotion:'reduce',trace:'retain-on-failure',screenshot:'only-on-failure'},
  projects: [
    {name:'desktop',use:{viewport:{width:1440,height:1000}}},
    {name:'wide',use:{viewport:{width:2048,height:1152}}},
    {name:'mobile',use:{viewport:{width:390,height:844},isMobile:true,hasTouch:true}},
    {name:'compact',use:{viewport:{width:320,height:900},isMobile:true,hasTouch:true}}
  ],
  webServer: {command:'python -m http.server 4173 --bind 127.0.0.1 --directory showcase',cwd:path.resolve(__dirname,'../..'),url:'http://127.0.0.1:4173',reuseExistingServer:false,stdout:'ignore',stderr:'pipe'}
});
