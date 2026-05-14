(function () {
  if (!window.KazixProfilePicture) {
    window.KazixProfilePicture = {};
  }

  function resolveApiBase() {
    if (window.KazixProfile && typeof window.KazixProfile.API_BASE === 'string') {
      return window.KazixProfile.API_BASE;
    }
    if (typeof window.KAZIX_API_BASE === 'string') {
      return window.KAZIX_API_BASE;
    }
    return 'https://kazix.onrender.com';
  }

  const API_BASE = resolveApiBase();

  class ProfilePictureHandler {
    constructor() {
      this.isUploading = false;
      this.currentEditFile = null;
      this.originalImageData = null;
      this.currentAvatarUrl = this.readCurrentAvatarUrl();
      this.setupEventListeners();
    }

    setupEventListeners() {
      document.addEventListener('click', (event) => {
        if (event.target.closest('.p-avatar-edit')) {
          this.openImageEditorModal();
        }
      });
    }

    openImageEditorModal() {
      let modal = document.getElementById('imageEditorModal');
      if (!modal) {
        modal = this.createEditorModal();
        document.body.appendChild(modal);
      }

      this.currentAvatarUrl = this.readCurrentAvatarUrl();
      modal.style.display = 'flex';
      document.body.style.overflow = 'hidden';

      document.getElementById('pictureFileInput').value = '';
      document.getElementById('editorControls').style.display = 'none';
      document.getElementById('imageCanvas').style.display = 'none';
      document.getElementById('imagePreview').style.display = 'none';
      document.getElementById('uploadBtn').style.display = 'none';
      document.getElementById('uploadProgress').style.display = 'none';
      document.getElementById('uploadBar').style.width = '0%';
      document.getElementById('uploadPercent').textContent = '0%';
      this.showFileError('');
      this.showUploadError('');
      this.updateDeleteButtonVisibility();
      this.resetEditorState();
    }

    createEditorModal() {
      const modal = document.createElement('div');
      modal.id = 'imageEditorModal';
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.7);
        display: none;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        padding: 1rem;
      `;

      modal.innerHTML = `
        <div style="background: white; border-radius: 8px; max-width: 600px; width: 100%; max-height: 90vh; overflow-y: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.2);">
          <div style="padding: 1.5rem; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; top: 0; background: white;">
            <h2 style="margin: 0; font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.25rem;">Update Profile Picture</h2>
            <button class="modal-close" type="button" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--muted);">✕</button>
          </div>

          <div style="padding: 1.5rem;">
            <div style="margin-bottom: 1.5rem;">
              <label style="display: block; font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem;">Select Image (JPG or PNG)</label>
              <input id="pictureFileInput" type="file" accept="image/jpeg,image/png" style="display: block; width: 100%; padding: 0.75rem; border: 2px dashed var(--border); border-radius: 4px; cursor: pointer;" />
              <div id="fileError" style="color: var(--rust); font-size: 0.8rem; margin-top: 0.5rem; display: none;"></div>
            </div>

            <div id="editorControls" style="display: none;">
              <div style="margin-bottom: 1.5rem; background: #f5f5f5; border-radius: 4px; overflow: hidden; display: flex; align-items: center; justify-content: center; min-height: 300px; position: relative;">
                <canvas id="imageCanvas" style="max-width: 100%; max-height: 400px; display: none;"></canvas>
                <img id="imagePreview" alt="Selected profile picture preview" style="max-width: 100%; max-height: 400px; display: none;" />
              </div>

              <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 1.5rem;">
                <button id="rotateLeftBtn" type="button" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer;">↺ Rotate</button>
                <button id="flipHBtn" type="button" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer;">↔ Flip H</button>
                <button id="flipVBtn" type="button" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer;">↕ Flip V</button>
                <button id="resetBtn" type="button" style="padding: 0.75rem; background: var(--cream); border: 1px solid var(--border); border-radius: 4px; font-weight: 600; cursor: pointer;">↻ Reset</button>
              </div>

              <div style="margin-bottom: 1.5rem;">
                <div style="margin-bottom: 1rem;">
                  <label style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.4rem;">
                    <span>Brightness</span>
                    <span id="brightnessValue">100%</span>
                  </label>
                  <input id="brightnessSlider" type="range" min="0" max="200" value="100" style="width: 100%; cursor: pointer;" />
                </div>

                <div style="margin-bottom: 1rem;">
                  <label style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.4rem;">
                    <span>Contrast</span>
                    <span id="contrastValue">100%</span>
                  </label>
                  <input id="contrastSlider" type="range" min="0" max="200" value="100" style="width: 100%; cursor: pointer;" />
                </div>

                <div>
                  <label style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.4rem;">
                    <span>Saturation</span>
                    <span id="saturationValue">100%</span>
                  </label>
                  <input id="saturationSlider" type="range" min="0" max="200" value="100" style="width: 100%; cursor: pointer;" />
                </div>
              </div>

              <div id="uploadProgress" style="display: none; margin-bottom: 1.5rem;">
                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; margin-bottom: 0.5rem;">
                  <span>Uploading...</span>
                  <span id="uploadPercent">0%</span>
                </div>
                <div style="height: 4px; background: var(--border); border-radius: 2px; overflow: hidden;">
                  <div id="uploadBar" style="height: 100%; background: var(--green); width: 0%; transition: width 0.2s;"></div>
                </div>
              </div>

              <div id="uploadError" style="background: rgba(192,57,43,0.1); border: 1px solid rgba(192,57,43,0.3); border-radius: 4px; padding: 0.75rem; color: var(--rust); font-size: 0.85rem; margin-bottom: 1.5rem; display: none;"></div>
            </div>

            <div style="display: flex; gap: 0.75rem; justify-content: flex-end; flex-wrap: wrap;">
              <button id="deleteBtn" type="button" style="padding: 0.75rem 1.5rem; background: transparent; color: var(--rust); border: 1px solid rgba(192,57,43,0.3); border-radius: 4px; font-family: 'Syne', sans-serif; font-weight: 600; cursor: pointer; display: none;">Remove Picture</button>
              <button class="modal-cancel" type="button" style="padding: 0.75rem 1.5rem; background: transparent; border: 1px solid var(--border); border-radius: 4px; font-family: 'Syne', sans-serif; font-weight: 600; cursor: pointer;">Cancel</button>
              <button id="uploadBtn" type="button" style="padding: 0.75rem 1.5rem; background: var(--ink); color: #F5F0E8; border: none; border-radius: 4px; font-family: 'Syne', sans-serif; font-weight: 600; cursor: pointer; display: none;">Save Picture</button>
            </div>
          </div>
        </div>
      `;

      this.setupModalListeners(modal);
      return modal;
    }

    setupModalListeners(modal) {
      const closeBtn = modal.querySelector('.modal-close');
      const cancelBtn = modal.querySelector('.modal-cancel');
      const deleteBtn = modal.querySelector('#deleteBtn');
      const fileInput = modal.querySelector('#pictureFileInput');
      const uploadBtn = modal.querySelector('#uploadBtn');

      closeBtn.addEventListener('click', () => this.closeModal());
      cancelBtn.addEventListener('click', () => this.closeModal());
      deleteBtn.addEventListener('click', () => this.deletePicture());
      fileInput.addEventListener('change', (event) => this.handleFileSelect(event));
      uploadBtn.addEventListener('click', () => this.uploadPicture());

      modal.querySelector('#rotateLeftBtn').addEventListener('click', () => this.rotateImage(-90));
      modal.querySelector('#flipHBtn').addEventListener('click', () => this.flipImageH());
      modal.querySelector('#flipVBtn').addEventListener('click', () => this.flipImageV());
      modal.querySelector('#resetBtn').addEventListener('click', () => this.resetImage());

      modal.querySelector('#brightnessSlider').addEventListener('input', (event) => {
        document.getElementById('brightnessValue').textContent = `${event.target.value}%`;
        this.updateImageFilters();
      });
      modal.querySelector('#contrastSlider').addEventListener('input', (event) => {
        document.getElementById('contrastValue').textContent = `${event.target.value}%`;
        this.updateImageFilters();
      });
      modal.querySelector('#saturationSlider').addEventListener('input', (event) => {
        document.getElementById('saturationValue').textContent = `${event.target.value}%`;
        this.updateImageFilters();
      });

      modal.addEventListener('click', (event) => {
        if (event.target === modal) {
          this.closeModal();
        }
      });
    }

    handleFileSelect(event) {
      const file = event.target.files[0];
      if (!file) return;

      this.showFileError('');
      this.showUploadError('');

      if (!['image/jpeg', 'image/png'].includes(file.type)) {
        this.resetEditorState();
        document.getElementById('editorControls').style.display = 'none';
        document.getElementById('uploadBtn').style.display = 'none';
        document.getElementById('imageCanvas').style.display = 'none';
        this.showFileError('Please select a JPG or PNG image.');
        return;
      }

      if (file.size > 5 * 1024 * 1024) {
        this.resetEditorState();
        document.getElementById('editorControls').style.display = 'none';
        document.getElementById('uploadBtn').style.display = 'none';
        document.getElementById('imageCanvas').style.display = 'none';
        this.showFileError('File is too large. Maximum size is 5 MB.');
        return;
      }

      this.currentEditFile = file;
      const reader = new FileReader();
      reader.onload = (loadEvent) => this.loadImageToEditor(loadEvent.target.result);
      reader.readAsDataURL(file);
    }

    loadImageToEditor(dataUrl) {
      const img = new Image();
      img.onload = () => {
        this.originalImageData = {
          dataUrl,
          width: img.width,
          height: img.height,
          rotation: 0,
          flipH: false,
          flipV: false,
        };

        document.getElementById('brightnessSlider').value = 100;
        document.getElementById('contrastSlider').value = 100;
        document.getElementById('saturationSlider').value = 100;
        document.getElementById('brightnessValue').textContent = '100%';
        document.getElementById('contrastValue').textContent = '100%';
        document.getElementById('saturationValue').textContent = '100%';
        document.getElementById('editorControls').style.display = 'block';
        document.getElementById('uploadBtn').style.display = 'inline-flex';
        document.getElementById('imagePreview').style.display = 'none';
        document.getElementById('fileError').style.display = 'none';
        this.updateImagePreview();
      };
      img.src = dataUrl;
    }

    rotateImage(degrees) {
      if (!this.originalImageData) return;
      this.originalImageData.rotation += degrees;
      this.updateImagePreview();
    }

    flipImageH() {
      if (!this.originalImageData) return;
      this.originalImageData.flipH = !this.originalImageData.flipH;
      this.updateImagePreview();
    }

    flipImageV() {
      if (!this.originalImageData) return;
      this.originalImageData.flipV = !this.originalImageData.flipV;
      this.updateImagePreview();
    }

    resetImage() {
      if (!this.originalImageData) return;
      this.originalImageData.rotation = 0;
      this.originalImageData.flipH = false;
      this.originalImageData.flipV = false;
      document.getElementById('brightnessSlider').value = 100;
      document.getElementById('contrastSlider').value = 100;
      document.getElementById('saturationSlider').value = 100;
      document.getElementById('brightnessValue').textContent = '100%';
      document.getElementById('contrastValue').textContent = '100%';
      document.getElementById('saturationValue').textContent = '100%';
      this.updateImagePreview();
    }

    currentFilterString() {
      const brightness = parseInt(document.getElementById('brightnessSlider').value, 10);
      const contrast = parseInt(document.getElementById('contrastSlider').value, 10);
      const saturation = parseInt(document.getElementById('saturationSlider').value, 10);
      return `brightness(${brightness}%) contrast(${contrast}%) saturate(${saturation}%)`;
    }

    updateImagePreview() {
      if (!this.originalImageData) return;

      const img = new Image();
      img.onload = () => {
        const canvas = document.getElementById('imageCanvas');
        const rotation = this.originalImageData.rotation;
        const flipH = this.originalImageData.flipH;
        const flipV = this.originalImageData.flipV;

        let width = img.width;
        let height = img.height;
        if (Math.abs(rotation) % 180 === 90) {
          width = img.height;
          height = img.width;
        }

        canvas.width = width;
        canvas.height = height;
        canvas.style.display = 'block';

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, width, height);
        ctx.save();
        ctx.translate(width / 2, height / 2);
        if (flipH) ctx.scale(-1, 1);
        if (flipV) ctx.scale(1, -1);
        ctx.rotate((rotation * Math.PI) / 180);
        ctx.filter = this.currentFilterString();
        ctx.drawImage(img, -img.width / 2, -img.height / 2);
        ctx.restore();
      };
      img.src = this.originalImageData.dataUrl;
    }

    updateImageFilters() {
      this.updateImagePreview();
    }

    async resolveAuthToken() {
      if (window.KazixProfile && typeof window.KazixProfile.getValidAccessToken === 'function') {
        try {
          return await window.KazixProfile.getValidAccessToken();
        } catch (_error) {
          return localStorage.getItem('kazix_access_token');
        }
      }
      return localStorage.getItem('kazix_access_token');
    }

    getUploadFilename() {
      const originalName = this.currentEditFile?.name || 'profile-picture.jpg';
      const nameParts = originalName.split('.');
      const extension = (nameParts.length > 1 ? nameParts.pop() : 'jpg').toLowerCase();
      const base = nameParts.join('.') || 'profile-picture';
      return `${base}.${extension === 'png' ? 'png' : 'jpg'}`;
    }

    getEditedBlob() {
      return new Promise((resolve, reject) => {
        const canvas = document.getElementById('imageCanvas');
        if (!canvas || !canvas.width || !canvas.height) {
          if (this.currentEditFile) {
            resolve(this.currentEditFile);
            return;
          }
          reject(new Error('No edited image is available to upload.'));
          return;
        }

        const mimeType = this.currentEditFile?.type === 'image/png' ? 'image/png' : 'image/jpeg';
        const quality = mimeType === 'image/png' ? undefined : 0.92;
        canvas.toBlob((blob) => {
          if (!blob) {
            reject(new Error('Could not prepare the edited image for upload.'));
            return;
          }
          resolve(blob);
        }, mimeType, quality);
      });
    }

    setBusyState(isBusy) {
      this.isUploading = isBusy;
      const uploadBtn = document.getElementById('uploadBtn');
      const deleteBtn = document.getElementById('deleteBtn');
      if (uploadBtn) uploadBtn.disabled = isBusy;
      if (deleteBtn) deleteBtn.disabled = isBusy;
      if (!isBusy) {
        document.getElementById('uploadProgress').style.display = 'none';
      }
    }

    safeJson(text) {
      try {
        return text ? JSON.parse(text) : {};
      } catch (_error) {
        return {};
      }
    }

    async uploadPicture() {
      if (!this.currentEditFile) {
        this.showUploadError('Choose an image first.');
        return;
      }

      if (this.isUploading) return;

      const token = await this.resolveAuthToken();
      if (!token) {
        this.showUploadError('Please sign in to upload a profile picture.');
        return;
      }

      this.showUploadError('');
      this.setBusyState(true);
      document.getElementById('uploadProgress').style.display = 'block';

      try {
        const editedBlob = await this.getEditedBlob();
        const formData = new FormData();
        formData.append('file', editedBlob, this.getUploadFilename());

        const xhr = new XMLHttpRequest();
        const response = await new Promise((resolve, reject) => {
          xhr.upload.addEventListener('progress', (event) => {
            if (!event.lengthComputable) return;
            const percent = Math.round((event.loaded / event.total) * 100);
            document.getElementById('uploadPercent').textContent = `${percent}%`;
            document.getElementById('uploadBar').style.width = `${percent}%`;
          });

          xhr.addEventListener('load', () => {
            const payload = this.safeJson(xhr.responseText);
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(payload);
              return;
            }
            reject(new Error(payload.detail || payload.message || 'Upload failed. Please try again.'));
          });

          xhr.addEventListener('error', () => {
            reject(new Error('Network error. Please check your connection.'));
          });

          xhr.open('POST', `${API_BASE}/v1/profiles/picture`);
          xhr.setRequestHeader('Authorization', `Bearer ${token}`);
          xhr.send(formData);
        });

        this.onUploadSuccess(response);
      } catch (error) {
        this.showUploadError(error.message || 'Upload failed.');
        this.setBusyState(false);
      }
    }

    async deletePicture() {
      if (this.isUploading) return;

      const hasPicture = Boolean(this.currentAvatarUrl || this.readCurrentAvatarUrl());
      if (!hasPicture) {
        this.showUploadError('There is no profile picture to remove.');
        return;
      }

      const token = await this.resolveAuthToken();
      if (!token) {
        this.showUploadError('Please sign in to manage your profile picture.');
        return;
      }

      this.showUploadError('');
      this.setBusyState(true);

      try {
        const response = await fetch(`${API_BASE}/v1/profiles/picture`, {
          method: 'DELETE',
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });

        const payload = this.safeJson(await response.text());
        if (!response.ok) {
          throw new Error(payload.detail || payload.message || 'Could not remove the profile picture.');
        }

        this.onDeleteSuccess(payload);
      } catch (error) {
        this.showUploadError(error.message || 'Could not remove the profile picture.');
        this.setBusyState(false);
      }
    }

    syncProfilePicture(profile) {
      const profileName = profile?.full_name || this.readProfileName();
      this.currentAvatarUrl = profile?.avatar_url || null;

      if (window.KazixProfile && typeof window.KazixProfile.invalidateProfileCache === 'function') {
        window.KazixProfile.invalidateProfileCache();
      }

      if (window.KazixProfile && typeof window.KazixProfile.setAvatarOnAll === 'function') {
        window.KazixProfile.setAvatarOnAll('.p-avatar', {
          name: profileName,
          avatarUrl: this.currentAvatarUrl,
        });
        window.KazixProfile.setAvatarOnAll('.topnav .user-avatar', {
          name: profileName,
          avatarUrl: this.currentAvatarUrl,
        });
        window.KazixProfile.setAvatarOnAll('.sidebar-bottom .sp-avatar', {
          name: profileName,
          avatarUrl: this.currentAvatarUrl,
        });
      } else {
        const fallback = this.initials(profileName);
        document.querySelectorAll('.p-avatar, .topnav .user-avatar, .sidebar-bottom .sp-avatar').forEach((element) => {
          if (this.currentAvatarUrl) {
            element.style.backgroundImage = `url("${String(this.currentAvatarUrl).replace(/"/g, '%22')}")`;
            element.style.backgroundSize = 'cover';
            element.style.backgroundPosition = 'center';
            element.style.backgroundRepeat = 'no-repeat';
            element.textContent = '';
          } else {
            element.style.backgroundImage = '';
            element.style.backgroundSize = '';
            element.style.backgroundPosition = '';
            element.style.backgroundRepeat = '';
            element.textContent = fallback;
          }
        });
      }

      this.updateDeleteButtonVisibility();
    }

    onUploadSuccess(profileData) {
      this.setBusyState(false);
      this.syncProfilePicture(profileData?.profile || {});
      this.closeModal();

      if (window.KazixErrorHandler) {
        window.KazixErrorHandler.showSuccess('Profile picture updated successfully!');
      }
    }

    onDeleteSuccess(profileData) {
      this.setBusyState(false);
      this.syncProfilePicture(profileData?.profile || {});
      this.closeModal();

      if (window.KazixErrorHandler) {
        window.KazixErrorHandler.showSuccess('Profile picture removed.');
      }
    }

    showFileError(message) {
      const errorEl = document.getElementById('fileError');
      if (!errorEl) return;
      errorEl.textContent = message || '';
      errorEl.style.display = message ? 'block' : 'none';
    }

    showUploadError(message) {
      const errorEl = document.getElementById('uploadError');
      if (!errorEl) return;
      errorEl.textContent = message || '';
      errorEl.style.display = message ? 'block' : 'none';
    }

    resetEditorState() {
      this.isUploading = false;
      this.currentEditFile = null;
      this.originalImageData = null;
    }

    closeModal() {
      const modal = document.getElementById('imageEditorModal');
      if (!modal) return;
      modal.style.display = 'none';
      document.body.style.overflow = '';
      this.resetEditorState();
    }

    updateDeleteButtonVisibility() {
      const deleteBtn = document.getElementById('deleteBtn');
      if (!deleteBtn) return;
      deleteBtn.style.display = (this.currentAvatarUrl || this.readCurrentAvatarUrl()) ? 'inline-flex' : 'none';
    }

    readCurrentAvatarUrl() {
      const avatar = document.querySelector('.p-avatar');
      if (!avatar) return null;
      const inline = avatar.style.backgroundImage || '';
      const match = inline.match(/url\(["']?(.*?)["']?\)/);
      return match && match[1] ? match[1] : null;
    }

    readProfileName() {
      const profileName = document.getElementById('profileName');
      if (profileName && profileName.textContent.trim()) {
        return profileName.textContent.trim();
      }
      const userName = document.querySelector('.topnav .user-name');
      if (userName && userName.textContent.trim()) {
        return userName.textContent.trim();
      }
      return 'My account';
    }

    initials(name) {
      const parts = String(name || '')
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2);
      if (!parts.length) return 'KX';
      return parts.map((part) => part.charAt(0).toUpperCase()).join('');
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      window.KazixProfilePicture.handler = new ProfilePictureHandler();
    });
  } else {
    window.KazixProfilePicture.handler = new ProfilePictureHandler();
  }

  window.KazixProfilePicture.openEditor = () => {
    if (window.KazixProfilePicture.handler) {
      window.KazixProfilePicture.handler.openImageEditorModal();
    }
  };
})();
