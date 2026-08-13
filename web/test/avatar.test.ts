import { describe, expect, it } from 'vitest'
import { avatarFileError, MAX_AVATAR_BYTES } from '../src/avatar'

describe('avatar file validation', () => {
  it('accepts supported image types within the local limit', () => {
    expect(avatarFileError(new File(['avatar'], 'avatar.webp', { type: 'image/webp' }))).toBeNull()
  })

  it('rejects unsupported types and oversized files', () => {
    expect(avatarFileError(new File(['avatar'], 'avatar.svg', { type: 'image/svg+xml' }))).toBe('Use a PNG, JPEG, or WebP profile picture.')
    expect(avatarFileError(new File([new Uint8Array(MAX_AVATAR_BYTES + 1)], 'avatar.png', { type: 'image/png' }))).toBe('Choose a profile picture smaller than 256 KB.')
  })
})
