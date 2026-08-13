export const MAX_AVATAR_BYTES = 256 * 1024
export const AVATAR_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

export function safeAvatarSource(value: string | undefined) {
  if (!value) return null
  const match = value.match(/^data:image\/(?:png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})$/)
  if (!match || match[1].length % 4 !== 0) return null
  return value
}

export function avatarFileError(file: File) {
  if (!AVATAR_TYPES.has(file.type)) return 'Use a PNG, JPEG, or WebP profile picture.'
  if (file.size > MAX_AVATAR_BYTES) return 'Choose a profile picture smaller than 256 KB.'
  return null
}
