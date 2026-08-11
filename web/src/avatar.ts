export const MAX_AVATAR_BYTES = 1_000_000
export const AVATAR_TYPES = new Set(['image/png', 'image/jpeg', 'image/webp'])

export function avatarFileError(file: File) {
  if (!AVATAR_TYPES.has(file.type)) return 'Use a PNG, JPEG, or WebP profile picture.'
  if (file.size > MAX_AVATAR_BYTES) return 'Choose a profile picture smaller than 1 MB.'
  return null
}
