function panelApp() {
  function applyIfPresent(s, fn) {
    if (!s) return;
    fn(s);
  }

  return {
    view: "main",
    busy: false,
    updateAvailable: false,
    statusMessage: "Ready",
    errorMessage: "",
    showSkipConfirm: false,
    newProfileName: "",
    enrollmentPreview: null,
    enrollmentPreviewMessage: "",
    enrollmentTimer: null,
    status: {
      tracking: false,
      paused: false,
      fps: null,
      confidence: null,
      last_calibrated: null,
      gaze_mode: "cursor_follow",
    },
    enrollment: {
      active: false,
      done: false,
      gesture_index: 0,
      gesture_count: 3,
      gesture_label: "",
      instruction: "",
      message: "",
    },
    settingsForm: {
      profile_name: "default",
      profiles: ["default"],
      kalman_measurement_noise: 10,
      saccade_threshold_px: 80,
      snap_radius_px: 50,
      scroll_speed_multiplier: 1,
      camera_index: 0,
      gaze_mode: "cursor_follow",
    },
    onboarding: {
      step_index: 0,
      step_count: 6,
      title: "",
      description: "",
      actions: [],
      skippable: false,
      skip_warning: "",
      notice: "",
    },
    applyStatus(s) {
      applyIfPresent(s, (s) => {
        this.statusMessage = s.message ?? "Ready";
        this.status = {
          tracking: !!s.tracking,
          paused: !!s.paused,
          fps: s.fps ?? null,
          confidence: s.confidence ?? null,
          last_calibrated: s.last_calibrated ?? null,
          gaze_mode: s.gaze_mode ?? "cursor_follow",
        };
      });
    },
    async init() {
      await this.refreshStatus();
      if (window.pywebview?.api) {
        const s = await window.pywebview.api.get_onboarding_state();
        this.applyOnboarding(s);
        if (s.should_show) this.view = "onboarding";
        await this.refreshUpdateBadge();
      }
    },
    applyEnrollment(s) {
      applyIfPresent(s, (s) => {
        this.enrollment = {
          active: !!s.active,
          done: !!s.done,
          gesture_index: s.gesture_index ?? 0,
          gesture_count: s.gesture_count ?? 3,
          gesture_label: s.gesture_label ?? "",
          instruction: s.instruction ?? "",
          message: s.message ?? "",
        };
      });
    },
    applyOnboarding(s) {
      applyIfPresent(s, (s) => {
        this.onboarding = {
          step_index: s.step_index ?? 0,
          step_count: s.step_count ?? 6,
          title: s.title ?? "",
          description: s.description ?? "",
          actions: s.actions ?? [],
          skippable: !!s.skippable,
          skip_warning: s.skip_warning ?? "",
          notice: s.notice ?? "",
        };
      });
    },
    applySettings(s) {
      applyIfPresent(s, (s) => {
        this.settingsForm = {
          profile_name: s.profile_name ?? "default",
          profiles: s.profiles ?? ["default"],
          kalman_measurement_noise: s.kalman_measurement_noise ?? 10,
          saccade_threshold_px: s.saccade_threshold_px ?? 80,
          snap_radius_px: s.snap_radius_px ?? 50,
          scroll_speed_multiplier: s.scroll_speed_multiplier ?? 1,
          camera_index: s.camera_index ?? 0,
          gaze_mode: s.gaze_mode ?? "cursor_follow",
        };
      });
    },
    async refreshStatus() {
      if (!window.pywebview?.api) return;
      const s = await window.pywebview.api.get_status();
      this.applyStatus(s);
      const v = await window.pywebview.api.get_view();
      if (v.view) this.view = v.view;
    },
    async refreshUpdateBadge() {
      if (!window.pywebview?.api) return;
      const r = await window.pywebview.api.check_for_updates();
      this.updateAvailable = !!r.available;
    },
    startEnrollmentPreviewPoll() {
      this.stopEnrollmentPreviewPoll();
      this.enrollmentTimer = setInterval(async () => {
        if (this.view !== "enrollment" || !window.pywebview?.api) return;
        const p = await window.pywebview.api.get_enrollment_preview();
        if (p.preview_jpeg) this.enrollmentPreview = p.preview_jpeg;
        this.enrollmentPreviewMessage = p.message ?? "";
      }, 250);
    },
    stopEnrollmentPreviewPoll() {
      if (this.enrollmentTimer) {
        clearInterval(this.enrollmentTimer);
        this.enrollmentTimer = null;
      }
    },
    async openEnrollmentView(payload) {
      if (payload?.enrollment) this.applyEnrollment(payload.enrollment);
      this.view = "enrollment";
      this.startEnrollmentPreviewPoll();
      if (payload?.message) this.statusMessage = payload.message;
    },
    async trainGestures() {
      await this.run(async () => {
        const r = await window.pywebview.api.show_enrollment();
        if (!r.ok) {
          this.errorMessage = r.message ?? "";
          return;
        }
        await this.openEnrollmentView(r);
      });
    },
    async captureEnrollment() {
      await this.run(async () => {
        const r = await window.pywebview.api.enrollment_capture();
        if (r.enrollment) this.applyEnrollment(r.enrollment);
        if (r.message) this.statusMessage = r.message;
        if (!r.ok) this.errorMessage = r.message ?? "";
      });
    },
    async leaveEnrollment() {
      await this.run(async () => {
        this.stopEnrollmentPreviewPoll();
        this.enrollmentPreview = null;
        const r = await window.pywebview.api.leave_enrollment();
        this.view = r.view ?? "main";
        if (r.view === "onboarding") {
          const s = await window.pywebview.api.get_onboarding_state();
          this.applyOnboarding(s);
        }
      });
    },
    async openSettings() {
      await this.run(async () => {
        await window.pywebview.api.show_settings();
        this.view = "settings";
        const s = await window.pywebview.api.get_settings_panel();
        this.applySettings(s);
      });
    },
    async saveSettings() {
      await this.run(async () => {
        const r = await window.pywebview.api.save_settings_panel({ ...this.settingsForm });
        if (r.settings) this.applySettings(r.settings);
        this.statusMessage = r.message ?? "Settings saved";
      });
    },
    applyProfileResult(r) {
      if (r.profiles) this.settingsForm.profiles = r.profiles;
      if (r.profile_name) this.settingsForm.profile_name = r.profile_name;
      if (!r.ok) this.errorMessage = r.message ?? "";
      return r.ok;
    },
    async createProfile() {
      await this.run(async () => {
        const r = await window.pywebview.api.create_profile(this.newProfileName);
        if (this.applyProfileResult(r)) {
          this.newProfileName = "";
          this.statusMessage = r.message ?? "";
        }
      });
    },
    async renameProfile() {
      const next = prompt("Rename profile to:", this.settingsForm.profile_name);
      if (!next) return;
      await this.run(async () => {
        const r = await window.pywebview.api.rename_profile(this.settingsForm.profile_name, next);
        if (this.applyProfileResult(r)) this.statusMessage = r.message ?? "";
      });
    },
    async deleteProfile() {
      if (!confirm("Delete profile " + this.settingsForm.profile_name + "?")) return;
      await this.run(async () => {
        const r = await window.pywebview.api.delete_profile(this.settingsForm.profile_name);
        if (this.applyProfileResult(r)) this.statusMessage = r.message ?? "";
      });
    },
    async activateProfile() {
      await this.run(async () => {
        const r = await window.pywebview.api.activate_profile(this.settingsForm.profile_name);
        this.applyProfileResult(r);
      });
    },
    async checkUpdates() {
      await this.run(async () => {
        const r = await window.pywebview.api.check_for_updates();
        this.updateAvailable = !!r.available;
        this.statusMessage = r.message ?? "";
        if (this.updateAvailable && confirm("Apply the available update now?")) {
          const applied = await window.pywebview.api.apply_update();
          this.updateAvailable = !!(applied.update && applied.update.available);
          this.statusMessage = applied.message ?? this.statusMessage;
        }
      });
    },
    async calibrate() {
      await this.run(async () => {
        const r = await window.pywebview.api.start_calibrate();
        this.statusMessage = r.message ?? "";
      });
    },
    async launch() {
      await this.run(async () => {
        const r = await window.pywebview.api.start_launch();
        await this.refreshStatus();
        this.statusMessage = r.message ?? "";
      });
    },
    async stopTracking() {
      await this.run(async () => {
        const r = await window.pywebview.api.stop_engine();
        await this.refreshStatus();
        this.statusMessage = r.message ?? "";
      });
    },
    async togglePause() {
      await this.run(async () => {
        const r = await window.pywebview.api.toggle_pause();
        if (r.message) this.statusMessage = r.message;
        await this.refreshStatus();
      });
    },
    async runOnboardingAction(id) {
      const map = {
        next: () => window.pywebview.api.onboarding_advance(),
        finish: () => window.pywebview.api.onboarding_complete(),
        check_camera: () => window.pywebview.api.onboarding_check_camera(),
        run_polynomial: () => window.pywebview.api.onboarding_run_polynomial(),
        run_offset: () => window.pywebview.api.onboarding_run_offset(),
        run_gestures: () => window.pywebview.api.onboarding_run_gestures(),
      };
      if (!map[id]) return;
      await this.run(async () => {
        const r = await map[id]();
        if (r.state) this.applyOnboarding(r.state);
        if (r.enrollment) await this.openEnrollmentView(r);
        else if (r.view === "enrollment") await this.openEnrollmentView(r);
        if (r.message) this.statusMessage = r.message;
        if (!r.ok && r.message) this.errorMessage = r.message;
        if (id === "finish") this.view = "main";
      });
    },
    async confirmSkip() {
      this.showSkipConfirm = false;
      await this.run(async () => {
        const r = await window.pywebview.api.onboarding_skip(true);
        if (r.state) this.applyOnboarding(r.state);
      });
    },
    async goMain() {
      if (window.pywebview?.api) {
        this.stopEnrollmentPreviewPoll();
        const r = await window.pywebview.api.show_main();
        this.view = r.view ?? "main";
      } else this.view = "main";
      this.errorMessage = "";
    },
    async run(fn) {
      if (!window.pywebview?.api) {
        this.errorMessage = "Python bridge unavailable";
        return;
      }
      this.busy = true;
      this.errorMessage = "";
      try {
        await fn();
      } catch (e) {
        this.errorMessage = String(e);
      } finally {
        this.busy = false;
      }
    },
  };
}
