import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'

export default tseslint.config(
  // Ignore patterns (equivalent to .eslintignore)
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
  },
  // Base TypeScript recommended rules
  ...tseslint.configs.recommended,
  // Project-specific config for src files
  {
    files: ['src/**/*.{ts,tsx}'],
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      // react-hooks v7 recommended (exhaustive-deps is warn, not error)
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // New react-hooks v7 rules — off until codebase is migrated
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/static-components': 'off',
      'react-hooks/refs': 'off',
      'react-hooks/immutability': 'off',
      // react-refresh: off — many files intentionally export both components and
      // utility constants (shadcn/ui pattern: badgeVariants, buttonVariants, etc.)
      'react-refresh/only-export-components': 'off',
      // TypeScript rules aligned with project conventions
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
)
