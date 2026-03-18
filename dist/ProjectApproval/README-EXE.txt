ProjectApproval Windows EXE

1. 双击 ProjectApproval.exe 启动。
2. 首次启动前可先编辑同级 .env。
3. 远程接口 token/JSESSIONID 也可在 runtime/config/integration_config.json 中维护，
   或启动后在“审批工作台”页面保存。
4. 浏览器访问地址默认是 http://127.0.0.1:8000/ui/approval

可外部修改的关键文件：
- .env
- runtime/config/integration_config.json
- data/*.xlsx