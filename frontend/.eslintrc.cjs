module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
    'plugin:tailwindcss/recommended',
  ],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  plugins: ['@typescript-eslint', 'react-refresh'],
  rules: {
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    // 暂时 warn，等有完整类型后再 error
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
    // 暂时关掉这些"过度严格"的规则，等基础功能稳定后再开：
    // - no-misused-promises: onClick 直接传 async 函数经常用，太繁琐
    // - no-floating-promises: fetch() 不 await 太常见
    // - no-base-to-string: 在动态 ID 渲染时常见
    '@typescript-eslint/no-misused-promises': 'off',
    '@typescript-eslint/no-floating-promises': 'off',
    '@typescript-eslint/no-base-to-string': 'off',
    'no-console': ['warn', { allow: ['warn', 'error', 'info'] }],
  },
  ignorePatterns: ['dist', 'node_modules', 'coverage', '*.config.js', '*.config.ts'],
};
