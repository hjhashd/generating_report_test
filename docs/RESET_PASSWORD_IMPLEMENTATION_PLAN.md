# 登录页修改密码功能实施计划

> **文档状态**：已完成  
> **制定日期**：2026-03-11  
> **实施日期**：2026-03-11  
> **功能说明**：在登录页面提供修改密码入口，用户输入账号+原密码验证身份后即可修改密码

---

## 一、功能概述

### 1.1 流程设计

```
┌─────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  点击修改密码  │ ──→ │  输入账号+原密码     │ ──→ │   验证通过          │
│  （登录页）   │     │  验证身份            │     │                     │
└─────────────┘     └─────────────────────┘     └──────────┬──────────┘
                                                           │
                                                           ↓
┌─────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  重置成功跳转  │ ←── │  输入新密码并确认    │ ←── │  进入新密码设置      │
│  到登录页     │     │                     │     │                     │
└─────────────┘     └─────────────────────┘     └─────────────────────┘
```

### 1.2 核心逻辑

1. 用户在**登录页**点击"修改密码"
2. 进入修改密码页面，输入**账号**和**原密码**
3. 后端验证账号和原密码是否匹配
4. 验证通过后，输入**新密码**和**确认密码**
5. 后端更新密码，返回成功
6. 跳回登录页，使用新密码登录

---

## 二、后端 API 设计

### 2.1 接口清单

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 修改密码 | POST | `/api/auth/change-password` | 验证账号+原密码，更新为新密码 |

### 2.2 请求/响应定义

#### 修改密码接口

**请求**：`POST /api/auth/change-password`

```json
{
  "username": "13800138000",
  "oldPassword": "原密码",
  "newPassword": "新密码",
  "confirmPassword": "确认新密码"
}
```

**成功响应**：
```json
{
  "code": 200,
  "message": "密码重置成功，请使用新密码登录",
  "data": null
}
```

**失败响应**：
```json
{
  "code": 400,
  "message": "账号或密码错误",
  "data": null
}
```

---

## 三、后端实现步骤

### 3.1 文件清单

```
ljt/prompt-system-backend/src/main/java/com/prompt/system/
├── controller/
│   └── AuthController.java              [修改：添加修改密码接口]
├── service/
│   └── UserService.java                 [修改：添加修改密码方法]
├── mapper/
│   └── UserMapper.java                  [修改：添加更新密码方法]
└── model/dto/
    └── ChangePasswordRequest.java        [新增：修改密码请求DTO]

ljt/prompt-system-backend/src/main/resources/mapper/
└── UserMapper.xml                       [修改：添加updatePassword SQL]
```

### 3.2 详细代码实现

#### 步骤1：创建 DTO 类

**文件**：`model/dto/ChangePasswordRequest.java`

```java
package com.prompt.system.model.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Data;

@Data
public class ChangePasswordRequest {
    @NotBlank(message = "账号不能为空")
    private String username;
    
    @NotBlank(message = "原密码不能为空")
    private String oldPassword;
    
    @NotBlank(message = "新密码不能为空")
    @Size(min = 6, message = "密码长度至少6位")
    @Pattern(regexp = "^(?=.*[a-zA-Z])(?=.*\\d).+$", message = "密码必须包含字母和数字")
    private String newPassword;
    
    @NotBlank(message = "确认密码不能为空")
    private String confirmPassword;
}
```

#### 步骤2：修改 UserMapper

**文件**：`mapper/UserMapper.java`

添加方法：

```java
void updatePassword(@Param("username") String username, @Param("passwordHash") String passwordHash);
```

**文件**：`resources/mapper/UserMapper.xml`

添加 SQL：

```xml
<update id="updatePassword">
    UPDATE users
    SET password_hash = #{passwordHash},
        updated_at = NOW()
    WHERE username = #{username}
      AND is_deleted = 0
</update>
```

#### 步骤3：修改 UserService

**文件**：`service/UserService.java`

添加方法：

```java
/**
 * 修改密码（无需登录）
 * @param username 账号
 * @param oldPassword 原密码
 * @param newPassword 新密码
 * @param confirmPassword 确认新密码
 */
public void changePassword(String username, String oldPassword, String newPassword, String confirmPassword) {
    // 验证两次新密码是否一致
    if (!newPassword.equals(confirmPassword)) {
        throw new IllegalArgumentException("两次输入的新密码不一致");
    }
    
    // 查询用户
    User user = userMapper.findByUsername(username);
    if (user == null) {
        throw new IllegalArgumentException("账号或密码错误");
    }
    
    if (user.getStatus() == 0) {
        throw new IllegalArgumentException("账号已被禁用");
    }
    
    // 验证原密码
    if (!passwordEncoder.matches(oldPassword, user.getPasswordHash())) {
        throw new IllegalArgumentException("账号或密码错误");
    }
    
    // 加密新密码并更新
    String passwordHash = passwordEncoder.encode(newPassword);
    userMapper.updatePassword(user.getUsername(), passwordHash);
}
```

#### 步骤4：修改 AuthController

**文件**：`controller/AuthController.java`

添加接口：

```java
@PostMapping("/change-password")
public Result<Void> changePassword(@RequestBody @Valid ChangePasswordRequest request) {
    userService.changePassword(
        request.getUsername(),
        request.getOldPassword(),
        request.getNewPassword(),
        request.getConfirmPassword()
    );
    return Result.success();
}
```

---

## 四、前端实现步骤

### 4.1 文件清单

```
ljt/note-prompt/src/
├── views/
│   ├── LoginView.vue                    [修改：更新"忘记密码"链接为"修改密码"]
│   └── ChangePasswordView.vue           [新增：修改密码页面]
├── router/
│   └── index.ts                         [修改：添加路由]
└── api/
    └── auth.ts                          [修改：添加API调用]
```

### 4.2 详细实现

#### 步骤1：创建 ChangePasswordView.vue

**文件**：`views/ChangePasswordView.vue`

```vue
<template>
  <div class="change-password-container min-h-screen flex items-center justify-center p-4">
    <!-- Background elements -->
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
      <div class="circle circle-3"></div>
    </div>

    <div class="change-password-card max-w-md w-full space-y-8 p-10 rounded-3xl shadow-2xl backdrop-blur-xl border border-white/20">
      <div class="text-center">
        <h2 class="text-3xl font-bold text-gray-900 mb-2">修改密码</h2>
        <p class="text-gray-500">请输入账号和原密码验证身份</p>
      </div>

      <form class="mt-8 space-y-6" @submit.prevent="handleChangePassword">
        <div class="space-y-4">
          <!-- 账号 -->
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1 ml-1">账号 / 电话号码</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-gray-400">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </span>
              <input
                v-model="form.username"
                type="text"
                required
                class="block w-full pl-10 pr-3 py-3 border border-gray-200 rounded-xl bg-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="请输入账号"
              />
            </div>
          </div>

          <!-- 原密码 -->
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1 ml-1">原密码</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-gray-400">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </span>
              <input
                v-model="form.oldPassword"
                type="password"
                required
                class="block w-full pl-10 pr-3 py-3 border border-gray-200 rounded-xl bg-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="请输入原密码"
              />
            </div>
          </div>

          <!-- 新密码 -->
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1 ml-1">新密码</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-gray-400">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
                </svg>
              </span>
              <input
                v-model="form.newPassword"
                type="password"
                required
                minlength="6"
                class="block w-full pl-10 pr-3 py-3 border border-gray-200 rounded-xl bg-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="至少6位，包含字母和数字"
              />
            </div>
          </div>

          <!-- 确认新密码 -->
          <div>
            <label class="block text-sm font-semibold text-gray-700 mb-1 ml-1">确认新密码</label>
            <div class="relative">
              <span class="absolute inset-y-0 left-0 pl-3 flex items-center text-gray-400">
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </span>
              <input
                v-model="form.confirmPassword"
                type="password"
                required
                class="block w-full pl-10 pr-3 py-3 border border-gray-200 rounded-xl bg-white/50 focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="请再次输入新密码"
              />
            </div>
          </div>
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="group relative w-full flex justify-center py-3 px-4 border border-transparent text-sm font-bold rounded-xl text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-blue-500/25"
        >
          <span v-if="loading" class="flex items-center">
            <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            重置中...
          </span>
          <span v-else>确认重置</span>
        </button>

        <div class="text-center text-sm">
          <router-link to="/login" class="font-medium text-blue-600 hover:text-blue-500 transition-colors">
            返回登录
          </router-link>
        </div>

        <div v-if="errorMsg" class="error-msg p-3 rounded-lg bg-red-50 text-red-500 text-sm text-center border border-red-100 animate-shake">
          {{ errorMsg }}
        </div>

        <div v-if="successMsg" class="p-3 rounded-lg bg-green-50 text-green-500 text-sm text-center border border-green-100">
          {{ successMsg }}
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { changePassword } from '@/api/auth'

const router = useRouter()

const form = reactive({
  username: '',
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

const handleChangePassword = async () => {
  // 前端验证
  if (form.newPassword !== form.confirmPassword) {
    errorMsg.value = '两次输入的新密码不一致'
    return
  }

  if (form.newPassword.length < 6) {
    errorMsg.value = '新密码长度至少6位'
    return
  }

  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''

  try {
    await changePassword(form)
    successMsg.value = '密码修改成功，正在跳转到登录页...'
    
    // 延迟后跳转到登录页
    setTimeout(() => {
      router.push('/login')
    }, 1500)
  } catch (error: any) {
    errorMsg.value = error.message || '重置失败，请检查账号和原密码'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.change-password-container {
  background-color: #f0f4f9;
  background-image: 
    radial-gradient(at 0% 0%, rgba(26, 115, 232, 0.05) 0, transparent 50%),
    radial-gradient(at 50% 0%, rgba(26, 115, 232, 0.05) 0, transparent 50%),
    radial-gradient(at 100% 0%, rgba(26, 115, 232, 0.05) 0, transparent 50%);
  position: relative;
  overflow: hidden;
}

.bg-decoration {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 0;
  pointer-events: none;
}

.circle {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
  animation: float 20s infinite alternate;
}

.circle-1 {
  width: 400px;
  height: 400px;
  background: #1a73e8;
  top: -100px;
  right: -100px;
}

.circle-2 {
  width: 300px;
  height: 300px;
  background: #8ab4f8;
  bottom: -50px;
  left: -50px;
  animation-delay: -5s;
}

.circle-3 {
  width: 250px;
  height: 250px;
  background: #e8f0fe;
  top: 40%;
  left: 20%;
  animation-delay: -10s;
}

@keyframes float {
  0% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -50px) scale(1.1); }
  66% { transform: translate(-20px, 20px) scale(0.9); }
  100% { transform: translate(0, 0) scale(1); }
}

.change-password-card {
  background: rgba(255, 255, 255, 0.8);
  position: relative;
  z-index: 1;
}

.animate-shake {
  animation: shake 0.5s cubic-bezier(.36,.07,.19,.97) both;
}

@keyframes shake {
  10%, 90% { transform: translate3d(-1px, 0, 0); }
  20%, 80% { transform: translate3d(2px, 0, 0); }
  30%, 50%, 70% { transform: translate3d(-4px, 0, 0); }
  40%, 60% { transform: translate3d(4px, 0, 0); }
}
</style>
```

#### 步骤2：修改 auth.ts API 文件

**文件**：`api/auth.ts`

添加方法：

```typescript
import request from '@/utils/request'

// 修改密码（无需登录）
export function changePassword(data: { 
  username: string
  oldPassword: string
  newPassword: string
  confirmPassword: string 
}) {
  return request({
    url: '/api/auth/change-password',
    method: 'post',
    data
  })
}
```

#### 步骤3：添加路由

**文件**：`router/index.ts`

添加路由：

```typescript
{
  path: '/change-password',
  name: 'ChangePassword',
  component: () => import('@/views/ChangePasswordView.vue'),
  meta: { public: true }
}  // 无需登录即可访问
}
```

#### 步骤4：修改 LoginView.vue

**文件**：`views/LoginView.vue`

将忘记密码链接改为修改密码：

```vue
<div class="text-sm">
  <router-link to="/change-password" class="font-medium text-blue-600 hover:text-blue-500 transition-colors">
    修改密码
  </router-link>
</div>
```

---

## 五、部署步骤

### 5.1 后端部署

```bash
cd /root/zzp/langextract-main/ljt/prompt-system-backend
./prod_service.sh restart
```

### 5.2 前端部署

```bash
cd /root/zzp/langextract-main/ljt/note-prompt
docker-compose -p note-prompt-prod -f docker-compose.prod.yml build --no-cache
docker-compose -p note-prompt-prod -f docker-compose.prod.yml up -d
```

---

## 六、安全注意事项

| 安全措施 | 说明 |
|----------|------|
| 原密码验证 | 必须输入正确的原密码才能重置 |
| 账号验证 | 验证账号是否存在且未被禁用 |
| 密码强度校验 | 至少6位，必须包含字母和数字 |
| 新密码一致性 | 两次输入的新密码必须一致 |
| 密码加密存储 | 使用BCrypt加密存储新密码 |
| 错误提示模糊化 | 账号或密码错误时使用统一提示，防止枚举账号 |

---

## 七、涉及文件汇总

### 后端（Java）

```
ljt/prompt-system-backend/src/main/java/com/prompt/system/
├── controller/AuthController.java                    [修改]
├── service/UserService.java                          [修改]
├── mapper/UserMapper.java                            [修改]
└── model/dto/ChangePasswordRequest.java               [新增]

ljt/prompt-system-backend/src/main/resources/mapper/
└── UserMapper.xml                                    [修改]
```

### 前端（Vue）

```
ljt/note-prompt/src/
├── views/
│   ├── LoginView.vue                                 [修改]
│   └── ChangePasswordView.vue                         [新增]
├── router/index.ts                                   [修改]
└── api/auth.ts                                       [修改]
```

---

## 八、实施记录

### 8.1 实施完成情况

| 项目 | 状态 | 说明 |
|------|------|------|
| 后端 ChangePasswordRequest DTO | ✅ 已完成 | 创建于 `model/dto/ChangePasswordRequest.java` |
| 后端 UserMapper 修改 | ✅ 已完成 | 添加 `updatePassword` 方法 |
| 后端 UserMapper.xml 修改 | ✅ 已完成 | 添加 `updatePassword` SQL |
| 后端 UserService 修改 | ✅ 已完成 | 添加 `changePassword` 方法 |
| 后端 AuthController 修改 | ✅ 已完成 | 添加 `POST /api/auth/change-password` 接口 |
| 前端 ChangePasswordView.vue | ✅ 已完成 | 创建修改密码页面 |
| 前端 auth.ts 修改 | ✅ 已完成 | 添加 `changePassword` API |
| 前端 router/index.ts 修改 | ✅ 已完成 | 添加 `/change-password` 路由 |
| 前端 LoginView.vue 修改 | ✅ 已完成 | 将"忘记密码"改为"修改密码"链接 |

### 8.2 部署说明

**后端部署**：
```bash
cd /root/zzp/langextract-main/ljt/prompt-system-backend
./restart_service.sh
```

**前端部署**：
```bash
cd /root/zzp/langextract-main/ljt/note-prompt
docker-compose -p note-prompt-prod -f docker-compose.prod.yml build --no-cache
docker-compose -p note-prompt-prod -f docker-compose.prod.yml up -d
```

> **注意**：部署后端服务需要执行 `restart_service.sh` 脚本，前端需要重新构建并启动 Docker 容器。

---

*文档制定时间：2026-03-11*  
*文档更新时间：2026-03-11*
