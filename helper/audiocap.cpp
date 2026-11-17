// audiocap.exe - kleiner WASAPI-Helfer fuer Potato Clips
//
//   audiocap list                 -> JSON: Aufnahme-/Wiedergabegeraete + Prozesse mit Audio-Sessions
//   audiocap process <pid>        -> Audio eines Prozesses (inkl. Kindprozesse) aufnehmen
//   audiocap loopback <id|default>-> alles, was auf einem Ausgabegeraet laeuft
//   audiocap mic <id|default>     -> Mikrofon / Eingabegeraet
//
// Capture-Ausgabe: rohes float32, Stereo, 48000 Hz, interleaved auf stdout.
// Der Helfer beendet sich, sobald stdin geschlossen wird (Elternprozess weg).

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <timeapi.h>
#include <initguid.h>
#include <mmdeviceapi.h>
#include <audioclient.h>
#include <audiopolicy.h>
#include <audioclientactivationparams.h>
#include <functiondiscoverykeys_devpkey.h>
#include <endpointvolume.h>
#include <propvarutil.h>
#include <io.h>
#include <fcntl.h>
#include <stdio.h>
#include <string>
#include <vector>
#include <atomic>
#include <cmath>
#include <set>
#include <map>
#include <mutex>
#include <algorithm>
#include <deque>
#include <condition_variable>
#include <chrono>
#include <thread>
#include <math.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "mmdevapi.lib")
#pragma comment(lib, "propsys.lib")
#pragma comment(lib, "winmm.lib")

static const int OUT_RATE = 48000;
static const int OUT_CH = 2;
static std::atomic<bool> g_quit{false};

static void logerr(const char* msg, HRESULT hr = S_OK) {
    fprintf(stderr, "audiocap: %s (hr=0x%08lX)\n", msg, (unsigned long)hr);
    fflush(stderr);
}

static std::string utf8(const wchar_t* w) {
    if (!w) return "";
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0, nullptr, nullptr);
    std::string s(n > 0 ? n - 1 : 0, '\0');
    if (n > 1) WideCharToMultiByte(CP_UTF8, 0, w, -1, &s[0], n, nullptr, nullptr);
    return s;
}

static std::wstring widen(const char* s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, nullptr, 0);
    std::wstring w(n > 0 ? n - 1 : 0, L'\0');
    if (n > 1) MultiByteToWideChar(CP_UTF8, 0, s, -1, &w[0], n);
    return w;
}

static std::string jsonEsc(const std::string& s) {
    std::string o;
    for (unsigned char c : s) {
        if (c == '"') o += "\\\"";
        else if (c == '\\') o += "\\\\";
        else if (c < 0x20) { char b[8]; sprintf_s(b, "\\u%04x", c); o += b; }
        else o += (char)c;
    }
    return o;
}

// ---------------------------------------------------------------- list
static void listDevices(IMMDeviceEnumerator* en, EDataFlow flow, std::string& out) {
    std::wstring defId;
    IMMDevice* def = nullptr;
    if (SUCCEEDED(en->GetDefaultAudioEndpoint(flow, eConsole, &def)) && def) {
        LPWSTR id = nullptr;
        if (SUCCEEDED(def->GetId(&id))) { defId = id; CoTaskMemFree(id); }
        def->Release();
    }
    IMMDeviceCollection* col = nullptr;
    out += "[";
    if (SUCCEEDED(en->EnumAudioEndpoints(flow, DEVICE_STATE_ACTIVE, &col))) {
        UINT n = 0; col->GetCount(&n);
        bool first = true;
        for (UINT i = 0; i < n; i++) {
            IMMDevice* d = nullptr;
            if (FAILED(col->Item(i, &d))) continue;
            LPWSTR id = nullptr; d->GetId(&id);
            std::string name = "?";
            IPropertyStore* ps = nullptr;
            if (SUCCEEDED(d->OpenPropertyStore(STGM_READ, &ps))) {
                PROPVARIANT pv; PropVariantInit(&pv);
                if (SUCCEEDED(ps->GetValue(PKEY_Device_FriendlyName, &pv)) && pv.vt == VT_LPWSTR)
                    name = utf8(pv.pwszVal);
                PropVariantClear(&pv);
                ps->Release();
            }
            float vol = -1.f;
            BOOL mute = FALSE;
            IAudioEndpointVolume* ev = nullptr;
            if (SUCCEEDED(d->Activate(__uuidof(IAudioEndpointVolume), CLSCTX_ALL, nullptr, (void**)&ev))) {
                ev->GetMasterVolumeLevelScalar(&vol);
                ev->GetMute(&mute);
                ev->Release();
            }
            char vb[80];
            sprintf_s(vb, ",\"volume\":%.3f,\"muted\":%s", vol, mute ? "true" : "false");
            if (!first) out += ",";
            first = false;
            out += "{\"id\":\"" + jsonEsc(utf8(id)) + "\",\"name\":\"" + jsonEsc(name) +
                   "\",\"default\":" + ((id && defId == id) ? "true" : "false") + vb + "}";
            if (id) CoTaskMemFree(id);
            d->Release();
        }
        col->Release();
    }
    out += "]";
}

static void listSessions(IMMDeviceEnumerator* en, std::string& out) {
    std::set<DWORD> seen;
    out += "[";
    bool first = true;
    IMMDeviceCollection* col = nullptr;
    if (SUCCEEDED(en->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &col))) {
        UINT n = 0; col->GetCount(&n);
        for (UINT i = 0; i < n; i++) {
            IMMDevice* d = nullptr;
            if (FAILED(col->Item(i, &d))) continue;
            LPWSTR devId = nullptr;
            d->GetId(&devId);
            std::string devIdU = jsonEsc(utf8(devId));
            if (devId) CoTaskMemFree(devId);
            IAudioSessionManager2* mgr = nullptr;
            if (SUCCEEDED(d->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, (void**)&mgr))) {
                IAudioSessionEnumerator* se = nullptr;
                if (SUCCEEDED(mgr->GetSessionEnumerator(&se))) {
                    int cnt = 0; se->GetCount(&cnt);
                    for (int k = 0; k < cnt; k++) {
                        IAudioSessionControl* c = nullptr;
                        if (FAILED(se->GetSession(k, &c))) continue;
                        IAudioSessionControl2* c2 = nullptr;
                        if (SUCCEEDED(c->QueryInterface(__uuidof(IAudioSessionControl2), (void**)&c2))) {
                            DWORD pid = 0;
                            AudioSessionState st = AudioSessionStateInactive;
                            c2->GetState(&st);
                            if (c2->IsSystemSoundsSession() != S_OK &&
                                SUCCEEDED(c2->GetProcessId(&pid)) && pid != 0 &&
                                st != AudioSessionStateExpired) {
                                // Pegel der Session (laeuft gerade Ton?)
                                float peak = 0.f;
                                IAudioMeterInformation* meter = nullptr;
                                if (SUCCEEDED(c->QueryInterface(__uuidof(IAudioMeterInformation), (void**)&meter))) {
                                    meter->GetPeakValue(&peak);
                                    meter->Release();
                                }
                                if (!first) out += ",";
                                first = false;
                                char b[160];
                                sprintf_s(b, "{\"pid\":%lu,\"active\":%s,\"peak\":%.4f,\"dev\":\"",
                                          (unsigned long)pid, st == AudioSessionStateActive ? "true" : "false",
                                          peak);
                                out += b;
                                out += devIdU + "\"}";
                                seen.insert(pid);
                            }
                            c2->Release();
                        }
                        c->Release();
                    }
                    se->Release();
                }
                mgr->Release();
            }
            d->Release();
        }
        col->Release();
    }
    out += "]";
}

static int cmdList() {
    IMMDeviceEnumerator* en = nullptr;
    HRESULT hr = CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                                  __uuidof(IMMDeviceEnumerator), (void**)&en);
    if (FAILED(hr)) { logerr("MMDeviceEnumerator", hr); return 2; }
    std::string out = "{\"capture\":";
    listDevices(en, eCapture, out);
    out += ",\"render\":";
    listDevices(en, eRender, out);
    out += ",\"sessions\":";
    listSessions(en, out);
    out += "}\n";
    en->Release();
    fwrite(out.data(), 1, out.size(), stdout);
    fflush(stdout);
    return 0;
}

// ---------------------------------------------------------------- process loopback activation
class ActivateHandler : public IActivateAudioInterfaceCompletionHandler, public IAgileObject {
    LONG ref = 1;
public:
    HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    HRESULT result = E_FAIL;
    IAudioClient* client = nullptr;
    ~ActivateHandler() { CloseHandle(done); }
    ULONG STDMETHODCALLTYPE AddRef() override { return InterlockedIncrement(&ref); }
    ULONG STDMETHODCALLTYPE Release() override {
        ULONG r = InterlockedDecrement(&ref);
        if (r == 0) delete this;
        return r;
    }
    HRESULT STDMETHODCALLTYPE QueryInterface(REFIID riid, void** ppv) override {
        if (riid == __uuidof(IUnknown) || riid == __uuidof(IActivateAudioInterfaceCompletionHandler)) {
            *ppv = static_cast<IActivateAudioInterfaceCompletionHandler*>(this);
        } else if (riid == __uuidof(IAgileObject)) {
            *ppv = static_cast<IAgileObject*>(this);
        } else { *ppv = nullptr; return E_NOINTERFACE; }
        AddRef();
        return S_OK;
    }
    HRESULT STDMETHODCALLTYPE ActivateCompleted(IActivateAudioInterfaceAsyncOperation* op) override {
        HRESULT hrAct = E_FAIL;
        IUnknown* unk = nullptr;
        HRESULT hr = op->GetActivateResult(&hrAct, &unk);
        if (SUCCEEDED(hr) && SUCCEEDED(hrAct) && unk) {
            result = unk->QueryInterface(__uuidof(IAudioClient), (void**)&client);
        } else {
            result = FAILED(hr) ? hr : hrAct;
        }
        if (unk) unk->Release();
        SetEvent(done);
        return S_OK;
    }
};

static HRESULT activateProcessClient(DWORD pid, IAudioClient** out) {
    AUDIOCLIENT_ACTIVATION_PARAMS params = {};
    params.ActivationType = AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK;
    params.ProcessLoopbackParams.TargetProcessId = pid;
    params.ProcessLoopbackParams.ProcessLoopbackMode = PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE;
    PROPVARIANT pv = {};
    pv.vt = VT_BLOB;
    pv.blob.cbSize = sizeof(params);
    pv.blob.pBlobData = (BYTE*)&params;

    ActivateHandler* h = new ActivateHandler();
    IActivateAudioInterfaceAsyncOperation* op = nullptr;
    HRESULT hr = ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, __uuidof(IAudioClient),
                                             &pv, h, &op);
    if (FAILED(hr)) { h->Release(); return hr; }
    WaitForSingleObject(h->done, 10000);
    hr = h->result;
    *out = h->client;
    if (op) op->Release();
    h->Release();
    if (SUCCEEDED(hr) && !*out) hr = E_FAIL;
    return hr;
}

// ---------------------------------------------------------------- format conversion
struct Converter {
    int inRate = OUT_RATE, inCh = OUT_CH;
    bool isFloat = true;
    int bits = 32;
    double pos = 0.0;       // fractional read position (resampling)
    float lastL = 0, lastR = 0;
    std::vector<float> stereo, out;

    void setup(const WAVEFORMATEX* wf) {
        inRate = wf->nSamplesPerSec;
        inCh = wf->nChannels;
        bits = wf->wBitsPerSample;
        isFloat = wf->wFormatTag == WAVE_FORMAT_IEEE_FLOAT;
        if (wf->wFormatTag == WAVE_FORMAT_EXTENSIBLE) {
            auto* ext = (const WAVEFORMATEXTENSIBLE*)wf;
            isFloat = IsEqualGUID(ext->SubFormat, KSDATAFORMAT_SUBTYPE_IEEE_FLOAT) != 0;
        }
    }
    float sample(const BYTE* p, size_t idx) const {
        if (isFloat) return ((const float*)p)[idx];
        if (bits == 16) return ((const int16_t*)p)[idx] / 32768.0f;
        if (bits == 32) return (float)(((const int32_t*)p)[idx] / 2147483648.0);
        if (bits == 24) {
            const BYTE* b = p + idx * 3;
            int32_t v = (b[0] << 8) | (b[1] << 16) | (b[2] << 24);
            return (float)(v / 2147483648.0);
        }
        return 0.f;
    }
    // returns interleaved stereo float32 @48k
    const std::vector<float>& convert(const BYTE* data, UINT32 frames, bool silent) {
        stereo.resize((size_t)frames * 2);
        for (UINT32 f = 0; f < frames; f++) {
            float l = 0, r = 0;
            if (!silent) {
                if (inCh == 1) { l = r = sample(data, f); }
                else {
                    l = sample(data, (size_t)f * inCh);
                    r = sample(data, (size_t)f * inCh + 1);
                    if (inCh > 2) { // einfache Downmix-Beimischung von Center etc.
                        float extra = 0;
                        for (int c = 2; c < inCh; c++) extra += sample(data, (size_t)f * inCh + c);
                        extra *= 0.5f / (inCh - 2);
                        l += extra; r += extra;
                    }
                }
            }
            stereo[(size_t)f * 2] = l;
            stereo[(size_t)f * 2 + 1] = r;
        }
        if (inRate == OUT_RATE) { out.swap(stereo); return out; }
        // lineares Resampling
        out.clear();
        double step = (double)inRate / OUT_RATE;
        while (pos < frames) {
            size_t i = (size_t)pos;
            double fr = pos - i;
            float l0 = stereo[i * 2], r0 = stereo[i * 2 + 1];
            float l1 = (i + 1 < frames) ? stereo[(i + 1) * 2] : l0;
            float r1 = (i + 1 < frames) ? stereo[(i + 1) * 2 + 1] : r0;
            out.push_back((float)(l0 + (l1 - l0) * fr));
            out.push_back((float)(r0 + (r1 - r0) * fr));
            pos += step;
        }
        pos -= frames;
        if (frames) { lastL = stereo[(frames - 1) * 2]; lastR = stereo[(frames - 1) * 2 + 1]; }
        return out;
    }
};

// ---------------------------------------------------------------- capture
// ---------------------------------------------------------------- IO-Abstraktion
// Standalone: rohe Daten auf stdout. Server: alle Streams in EINEM Prozess, gerahmte Pakete.
struct StreamIO {
    virtual ~StreamIO() {}
    virtual void log(const std::string& msg) = 0;
    virtual bool emit(const float* data, size_t nfloats) = 0;     // false = beenden
    virtual bool stopped() = 0;
    virtual bool request(uint32_t frames, float* out) = 0;        // Wiedergabe: Daten holen
};

static void iolog(StreamIO& io, const char* msg, HRESULT hr = S_OK) {
    char b[300];
    sprintf_s(b, "audiocap: %s (hr=0x%08lX)", msg, (unsigned long)hr);
    io.log(b);
}

static DWORD WINAPI stdinWatch(LPVOID) {
    char buf[64];
    HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
    DWORD rd = 0;
    while (ReadFile(in, buf, sizeof(buf), &rd, nullptr) && rd > 0) {}
    g_quit = true;
    return 0;
}

static WAVEFORMATEX makeFormat(bool flt) {
    WAVEFORMATEX wf = {};
    wf.wFormatTag = flt ? WAVE_FORMAT_IEEE_FLOAT : WAVE_FORMAT_PCM;
    wf.nChannels = OUT_CH;
    wf.nSamplesPerSec = OUT_RATE;
    wf.wBitsPerSample = flt ? 32 : 16;
    wf.nBlockAlign = wf.nChannels * wf.wBitsPerSample / 8;
    wf.nAvgBytesPerSec = wf.nSamplesPerSec * wf.nBlockAlign;
    return wf;
}

static IMMDevice* getDevice(EDataFlow flow, const char* idArg) {
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                                __uuidof(IMMDeviceEnumerator), (void**)&en))) return nullptr;
    IMMDevice* d = nullptr;
    if (!idArg || !*idArg || _stricmp(idArg, "default") == 0)
        en->GetDefaultAudioEndpoint(flow, eConsole, &d);
    else
        en->GetDevice(widen(idArg).c_str(), &d);
    en->Release();
    return d;
}

static bool readExact(HANDLE h, void* buf, DWORD bytes) {
    BYTE* p = (BYTE*)buf;
    while (bytes > 0) {
        DWORD rd = 0;
        if (!ReadFile(h, p, bytes, &rd, nullptr) || rd == 0) return false;
        p += rd;
        bytes -= rd;
    }
    return true;
}

static bool writeExact(HANDLE h, const void* buf, DWORD bytes) {
    const BYTE* p = (const BYTE*)buf;
    while (bytes > 0) {
        DWORD wr = 0;
        if (!WriteFile(h, p, bytes, &wr, nullptr) || wr == 0) return false;
        p += wr;
        bytes -= wr;
    }
    return true;
}

// Sitzung in Windows benennen (Lautstaerkemixer zeigt dann "Potato Clips")
static void nameSession(IAudioClient* client) {
    IAudioSessionControl* sc = nullptr;
    if (SUCCEEDED(client->GetService(__uuidof(IAudioSessionControl), (void**)&sc)) && sc) {
        sc->SetDisplayName(L"Potato Clips", nullptr);
        wchar_t exe[MAX_PATH];
        if (GetModuleFileNameW(nullptr, exe, MAX_PATH)) {
            std::wstring icon = std::wstring(exe) + L",0";
            sc->SetIconPath(icon.c_str(), nullptr);
        }
        sc->Release();
    }
}

static int runCapture(const char* mode, const char* arg, StreamIO& io) {
    const REFERENCE_TIME bufDur = 2000000; // 200 ms
    IAudioClient* client = nullptr;
    Converter conv;
    HRESULT hr;
    bool isProcess = strcmp(mode, "process") == 0;

    if (isProcess) {
        DWORD pid = (DWORD)strtoul(arg, nullptr, 10);
        hr = activateProcessClient(pid, &client);
        if (FAILED(hr)) { iolog(io, "Prozess-Loopback aktivieren fehlgeschlagen", hr); return 3; }
        bool ok = false;
        for (int flt = 1; flt >= 0 && !ok; flt--) {
            WAVEFORMATEX wf = makeFormat(flt == 1);
            hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
                                    AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM |
                                    AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                                    bufDur, 0, &wf, nullptr);
            if (SUCCEEDED(hr)) { conv.setup(&wf); ok = true; }
            else if (flt == 1) { // Client neu holen, Initialize darf nur einmal
                client->Release(); client = nullptr;
                if (FAILED(activateProcessClient(pid, &client))) break;
            }
        }
        if (!ok) { iolog(io, "Prozess-Loopback Initialize fehlgeschlagen", hr); if (client) client->Release(); return 3; }
    } else {
        bool loop = strcmp(mode, "loopback") == 0;
        IMMDevice* dev = getDevice(loop ? eRender : eCapture, arg);
        if (!dev) { iolog(io, "Geraet nicht gefunden"); return 4; }
        hr = dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, (void**)&client);
        if (FAILED(hr)) { dev->Release(); iolog(io, "Activate", hr); return 4; }
        DWORD flags = loop ? AUDCLNT_STREAMFLAGS_LOOPBACK : 0;
        WAVEFORMATEX wf = makeFormat(true);
        hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
                                flags | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                                bufDur, 0, &wf, nullptr);
        if (SUCCEEDED(hr)) {
            conv.setup(&wf);
        } else {
            // Fallback: natives Mixformat und selbst konvertieren
            client->Release(); client = nullptr;
            hr = dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, (void**)&client);
            WAVEFORMATEX* mix = nullptr;
            if (SUCCEEDED(hr)) hr = client->GetMixFormat(&mix);
            if (SUCCEEDED(hr)) hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED, flags, bufDur, 0, mix, nullptr);
            if (FAILED(hr)) { dev->Release(); if (client) client->Release(); iolog(io, "Initialize", hr); return 4; }
            conv.setup(mix);
            CoTaskMemFree(mix);
        }
        dev->Release();
    }
    nameSession(client);

    IAudioCaptureClient* cap = nullptr;
    hr = client->GetService(__uuidof(IAudioCaptureClient), (void**)&cap);
    if (FAILED(hr)) { iolog(io, "GetService", hr); client->Release(); return 5; }
    hr = client->Start();
    if (FAILED(hr)) { iolog(io, "Start", hr); cap->Release(); client->Release(); return 5; }

    char okmsg[400];
    sprintf_s(okmsg, "audiocap: ok %s %s rate=%d ch=%d", mode, arg ? arg : "", conv.inRate, conv.inCh);
    io.log(okmsg);

    int rc = 0;
    while (!io.stopped()) {
        Sleep(5);
        UINT32 packet = 0;
        hr = cap->GetNextPacketSize(&packet);
        if (FAILED(hr)) { iolog(io, "GetNextPacketSize (Geraet/Prozess weg?)", hr); rc = 6; break; }
        bool fail = false;
        while (packet > 0) {
            BYTE* data = nullptr;
            UINT32 frames = 0;
            DWORD flags = 0;
            hr = cap->GetBuffer(&data, &frames, &flags, nullptr, nullptr);
            if (FAILED(hr)) break;
            const auto& out = conv.convert(data, frames, (flags & AUDCLNT_BUFFERFLAGS_SILENT) != 0);
            cap->ReleaseBuffer(frames);
            if (!out.empty() && !io.emit(out.data(), out.size())) { fail = true; break; }
            if (FAILED(cap->GetNextPacketSize(&packet))) break;
        }
        if (fail) break;
    }
    client->Stop();
    cap->Release();
    client->Release();
    return rc;
}

// Wiedergabe (pull-Modell): der Helfer fragt N Frames an und bekommt float32 Stereo 48 kHz.
static int runPlay(const char* arg, StreamIO& io) {
    IMMDevice* dev = getDevice(eRender, arg);
    if (!dev) { iolog(io, "Ausgabegeraet nicht gefunden"); return 4; }
    IAudioClient* client = nullptr;
    HRESULT hr = dev->Activate(__uuidof(IAudioClient), CLSCTX_ALL, nullptr, (void**)&client);
    dev->Release();
    if (FAILED(hr)) { iolog(io, "Activate", hr); return 4; }
    WAVEFORMATEX wf = makeFormat(true);
    const REFERENCE_TIME bufDur = 400000; // 40 ms (Python-Daten kommen aus einem eigenen Vorrat)
    hr = client->Initialize(AUDCLNT_SHAREMODE_SHARED,
                            AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY,
                            bufDur, 0, &wf, nullptr);
    if (FAILED(hr)) { iolog(io, "Initialize (Wiedergabe)", hr); client->Release(); return 4; }
    UINT32 bufFrames = 0;
    client->GetBufferSize(&bufFrames);
    IAudioRenderClient* render = nullptr;
    hr = client->GetService(__uuidof(IAudioRenderClient), (void**)&render);
    if (FAILED(hr)) { iolog(io, "GetService (Wiedergabe)", hr); client->Release(); return 5; }
    {
        // Windows merkt sich pro App und Geraet eine Lautstaerke (Lautstaerkemixer) - immer 100 % nutzen
        ISimpleAudioVolume* sv = nullptr;
        if (SUCCEEDED(client->GetService(__uuidof(ISimpleAudioVolume), (void**)&sv))) {
            sv->SetMasterVolume(1.0f, nullptr);
            sv->SetMute(FALSE, nullptr);
            sv->Release();
        }
    }
    nameSession(client);

    std::vector<float> tmp;
    char okmsg[300];
    sprintf_s(okmsg, "audiocap: ok play %s buffer=%u", arg ? arg : "", bufFrames);
    io.log(okmsg);
    bool started = false;
    int rc = 0;
    while (!io.stopped()) {
        UINT32 pad = 0;
        hr = client->GetCurrentPadding(&pad);
        if (FAILED(hr)) { iolog(io, "GetCurrentPadding (Geraet weg?)", hr); rc = 6; break; }
        UINT32 avail = bufFrames - pad;
        if (avail >= 240 || !started) {
            if (avail == 0) { Sleep(2); continue; }
            tmp.resize((size_t)avail * 2);
            if (!io.request(avail, tmp.data())) break;
            BYTE* data = nullptr;
            hr = render->GetBuffer(avail, &data);
            if (FAILED(hr)) { iolog(io, "GetBuffer (Wiedergabe)", hr); rc = 6; break; }
            memcpy(data, tmp.data(), (size_t)avail * 8);
            render->ReleaseBuffer(avail, 0);
            if (!started) {
                hr = client->Start();
                if (FAILED(hr)) { iolog(io, "Start (Wiedergabe)", hr); rc = 6; break; }
                started = true;
            }
        }
        Sleep(4);
    }
    client->Stop();
    render->Release();
    client->Release();
    return rc;
}

// ---------------------------------------------------------------- Standalone-IO (ein Stream pro Prozess)
struct StandaloneIO : StreamIO {
    void log(const std::string& msg) override {
        fprintf(stderr, "%s\n", msg.c_str());
        fflush(stderr);
    }
    bool emit(const float* d, size_t n) override {
        if (fwrite(d, sizeof(float), n, stdout) != n) return false;
        return fflush(stdout) == 0;
    }
    bool stopped() override { return g_quit; }
    bool request(uint32_t frames, float* out) override {
        HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
        HANDLE outH = GetStdHandle(STD_OUTPUT_HANDLE);
        if (!writeExact(outH, &frames, 4)) return false;
        return readExact(in, out, frames * 8);
    }
};

static int cmdCapture(const char* mode, const char* arg) {
    CreateThread(nullptr, 0, stdinWatch, nullptr, 0, nullptr);
    StandaloneIO io;
    return runCapture(mode, arg, io);
}

static int cmdPlay(const char* arg) {
    StandaloneIO io;
    return runPlay(arg, io);
}

// ---------------------------------------------------------------- Server: alle Streams in einem Prozess
// Paket: [typ u8][id u16][laenge u32][daten]
//  -> stdin : 1 = Befehl ("start <mode> <arg>" / "stop"), 2 = Wiedergabe-Daten (float32)
//  <- stdout: 1 = Audio (float32), 2 = Log-Zeile, 3 = Datenanfrage (u32 Frames), 4 = Stream beendet,
//             5 = Stille (u32 Frames), 6 = Stimm-Pegel (2x float: Mikro, mit Filter)
// Ausgabe ueber eigenen Schreib-Thread: kein Audio-Thread wartet jemals auf die Pipe zu Python.
// (Vorher blockierte die Wiedergabe, wenn Python kurz hing und die Pipe voll war -> Stimme abgehackt.)
static std::mutex g_outLock;
static std::condition_variable g_outCv;
static std::deque<std::vector<BYTE>> g_outQ;
static size_t g_outBytes = 0;
static std::atomic<unsigned> g_outDropped{0};
static std::once_flag g_writerOnce;

static DWORD WINAPI writerThread(LPVOID) {
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
    std::vector<BYTE> buf;
    for (;;) {
        {
            std::unique_lock<std::mutex> lk(g_outLock);
            while (g_outQ.empty()) {
                if (g_quit) return 0;
                g_outCv.wait_for(lk, std::chrono::milliseconds(100));
            }
            buf.swap(g_outQ.front());
            g_outQ.pop_front();
            g_outBytes -= buf.size();
        }
        if (!writeExact(h, buf.data(), (DWORD)buf.size())) { g_quit = true; return 0; }
        buf.clear();
    }
}

static bool sendFrame(uint8_t type, uint16_t id, const void* data, uint32_t len) {
    if (g_quit) return false;
    std::call_once(g_writerOnce, [] {
        HANDLE th = CreateThread(nullptr, 0, writerThread, nullptr, 0, nullptr);
        if (th) { SetThreadPriority(th, THREAD_PRIORITY_ABOVE_NORMAL); CloseHandle(th); }
    });
    std::vector<BYTE> f(7 + (size_t)len);
    f[0] = type;
    memcpy(f.data() + 1, &id, 2);
    memcpy(f.data() + 3, &len, 4);
    if (len) memcpy(f.data() + 7, data, len);
    {
        std::lock_guard<std::mutex> lk(g_outLock);
        // Notbremse: haengt Python sehr lange (> ~10 s Audio im Stau), alte Audiodaten verwerfen
        if (type == 1 && g_outBytes > 48u * 1024 * 1024) { g_outDropped++; return true; }
        g_outBytes += f.size();
        g_outQ.push_back(std::move(f));
    }
    g_outCv.notify_one();
    return true;
}

// Rest der Warteschlange noch rausschreiben (beim Beenden)
static void flushOut(DWORD maxMs) {
    ULONGLONG t0 = GetTickCount64();
    for (;;) {
        { std::lock_guard<std::mutex> lk(g_outLock); if (g_outQ.empty()) return; }
        if (GetTickCount64() - t0 > maxMs) return;
        Sleep(5);
    }
}

// Messwerte: laengste Pause zwischen zwei Abrufen der Wiedergabe / zwei Mikro-Paketen (ms)
static std::atomic<unsigned> g_renderGapMax{0}, g_micGapMax{0};
static double nowMs() {
    static LARGE_INTEGER f = [] { LARGE_INTEGER x; QueryPerformanceFrequency(&x); return x; }();
    LARGE_INTEGER c; QueryPerformanceCounter(&c);
    return (double)c.QuadPart * 1000.0 / (double)f.QuadPart;
}
static void noteGap(std::atomic<unsigned>& mx, double& last) {
    double t = nowMs();
    if (last > 0) {
        unsigned g = (unsigned)(t - last);
        unsigned cur = mx.load();
        while (g > cur && !mx.compare_exchange_weak(cur, g)) {}
    }
    last = t;
}

// ---------------------------------------------------------------- Native Stimme (ohne Python im Echtzeitpfad)
// Mikro -> Rumpelfilter -> RNNoise -> sanftes Gate -> Ring -> wird in den Discord-Ausgang gemischt.
typedef void* (*rn_create_t)(void*);
typedef float (*rn_process_t)(void*, float*, const float*);
typedef void (*rn_destroy_t)(void*);
static rn_create_t rn_create = nullptr;
static rn_process_t rn_process = nullptr;
static rn_destroy_t rn_destroy = nullptr;

static bool loadRnnoise() {
    static int state = 0;
    if (state) return state == 1;
    wchar_t p[MAX_PATH];
    GetModuleFileNameW(nullptr, p, MAX_PATH);
    std::wstring dir(p);
    dir = dir.substr(0, dir.find_last_of(L"\\/") + 1);
    HMODULE h = LoadLibraryW((dir + L"rnnoise.dll").c_str());
    if (h) {
        rn_create = (rn_create_t)GetProcAddress(h, "rnnoise_create");
        rn_process = (rn_process_t)GetProcAddress(h, "rnnoise_process_frame");
        rn_destroy = (rn_destroy_t)GetProcAddress(h, "rnnoise_destroy");
    }
    state = (rn_create && rn_process && rn_destroy) ? 1 : 2;
    return state == 1;
}

struct VoiceSettings {
    std::atomic<bool> enabled{false};
    std::atomic<bool> clean{true};
    std::atomic<bool> gate{true};
    std::atomic<float> strength{0.85f};
    std::atomic<float> gain{1.0f};
    std::atomic<int> target{-1};
    // 0 = alles nativ, 2 = Stimmeffekt im eigenen Effekt-Prozess (fxworker)
    std::atomic<int> pymode{0};
    std::atomic<bool> monitor{false};    // mich selbst hoeren (Kopfhoerer)
    std::atomic<float> monGain{0.8f};
    std::atomic<int> monTarget{-1};
};
static VoiceSettings g_voice;

// Ring fuer Mono-Audio mit weichem Aus-/Einblenden bei Luecken.
// Taktausgleich: Mikro und virtuelles Kabel laufen auf leicht unterschiedlichen Uhren (z. B. 48000 vs 48020 Hz).
// Ohne Ausgleich laeuft der Puffer langsam leer (Abriss) oder voll (Sprung) - alle paar Minuten ein Aussetzer.
// Darum wird minimal schneller/langsamer ausgelesen (max. 0,5 %, unhoerbar), sodass der Fuellstand am Ziel bleibt.
struct MonoRing {
    std::mutex m;
    std::vector<float> b;
    size_t r = 0, n = 0;
    double fpos = 0.0;               // Bruchteil-Leseposition (fuer den Taktausgleich)
    double avg = -1.0;               // geglaetteter Fuellstand
    double ratio = 1.0;
    bool priming = true, fadeIn = true;
    size_t maxN, targetN, primeN;
    unsigned underruns = 0, drops = 0;
    MonoRing(size_t cap, size_t mx, size_t tg, size_t pr) : b(cap), maxN(mx), targetN(tg), primeN(pr) {}
    void setParams(size_t mx, size_t tg, size_t pr) {
        std::lock_guard<std::mutex> lk(m);
        if (mx > b.size() - 2) mx = b.size() - 2;
        maxN = mx; targetN = tg; primeN = pr;
        avg = -1.0;
    }
    void push(const float* x, size_t k) {
        std::lock_guard<std::mutex> lk(m);
        size_t cap = b.size();
        if (k > maxN) { x += k - maxN; k = maxN; }
        if (n + k > maxN) {   // viel zu viel Verzoegerung (z. B. nach einem Haenger) -> auf Ziel zuruecksetzen
            size_t keep = targetN > k ? targetN - k : 0;
            if (n > keep) { size_t drop = n - keep; r = (r + drop) % cap; n = keep; drops++; fadeIn = true; fpos = 0; avg = -1.0; }
        }
        for (size_t i = 0; i < k; i++) b[(r + n + i) % cap] = x[i];
        n += k;
    }
    void read(float* out, size_t k) {
        std::lock_guard<std::mutex> lk(m);
        size_t cap = b.size();
        if (priming) {
            if (n < primeN) { memset(out, 0, k * sizeof(float)); return; }
            priming = false;
            avg = -1.0;
        }
        // Fuellstand glaetten (~1 s) und Lesegeschwindigkeit sanft nachregeln
        double fill = (double)n;
        if (avg < 0) avg = fill;
        double a = (double)k / 48000.0;           // Glaettung pro Aufruf, Zeitkonstante ~1 s
        avg += (fill - avg) * (a > 1.0 ? 1.0 : a);
        double err = (avg - (double)targetN) / 48000.0;      // Sekunden zu viel/zu wenig
        ratio = 1.0 + err * 0.08;                            // 20 ms zu viel -> 0,16 % schneller
        if (ratio > 1.005) ratio = 1.005;
        if (ratio < 0.995) ratio = 0.995;
        size_t got = 0;
        double p = fpos;
        for (; got < k; got++) {
            size_t i0 = (size_t)p;
            if (i0 + 1 >= n) break;
            double fr = p - (double)i0;
            float x0 = b[(r + i0) % cap], x1 = b[(r + i0 + 1) % cap];
            out[got] = x0 + (x1 - x0) * (float)fr;
            p += ratio;
        }
        size_t used = (size_t)p;
        if (used > n) used = n;
        r = (r + used) % cap;
        n -= used;
        fpos = p - (double)used;
        for (size_t i = got; i < k; i++) out[i] = 0.f;
        const size_t F = 96;
        if (fadeIn && got) {
            size_t mm = (std::min)(F, got);
            for (size_t i = 0; i < mm; i++) out[i] *= (float)i / mm;
            fadeIn = false;
        }
        if (got < k) {
            size_t mm = (std::min)(F, got);
            for (size_t i = 0; i < mm; i++) out[got - mm + i] *= 1.0f - (float)(i + 1) / mm;
            priming = true;
            fadeIn = true;
            fpos = 0;
            underruns++;
        }
    }
    void clear() {
        std::lock_guard<std::mutex> lk(m);
        n = 0; priming = true; fadeIn = true; fpos = 0; avg = -1.0;
    }
    void info(double& fillMs, double& ppm) {
        std::lock_guard<std::mutex> lk(m);
        fillMs = (avg < 0 ? (double)n : avg) / 48.0;
        ppm = (ratio - 1.0) * 1e6;
    }
};
// normal: max 150 ms, Ziel 40 ms, Start ab 30 ms (mit Stimmeffekt ueber Python: groesser, siehe voiceconf)
static MonoRing g_voiceRing(48000, 7200, 1920, 1440);
static MonoRing g_monRing(48000, 7200, 1920, 1440);      // Mithoeren auf den Kopfhoerern

// fertige Stimme (mit oder ohne Effekt) an Discord und/oder Kopfhoerer
static void pushVoice(const float* d, size_t n) {
    if (g_voice.enabled) g_voiceRing.push(d, n);
    if (g_voice.monitor) g_monRing.push(d, n);
}

// ---------------------------------------------------------------- Effekt-Prozess
// Der Stimmeffekt (Python/numpy) laeuft in einem EIGENEN Prozess, der nur das tut. Die Haupt-App
// (Oberflaeche, Quellen-Scan, Clips) kann ihn so nicht mehr ausbremsen. Der Helfer spricht direkt mit ihm.
//  -> Worker stdin : [u8 typ][u32 len][daten]  typ 1 = Mono-Block float32, typ 2 = Text ("set potato 0.6")
//  <- Worker stdout: [u32 len][daten]          Mono-Block float32 (len 0 = "bin bereit")
struct FxWorker {
    std::mutex m;
    HANDLE proc = nullptr, inW = nullptr, outR = nullptr, job = nullptr;
    std::string lastSet;
    std::atomic<bool> running{false}, ready{false};
    std::atomic<int> outstanding{0};
    std::atomic<unsigned> restarts{0}, skipped{0};
    ULONGLONG lastStart = 0;

    bool writeMsg(uint8_t type, const void* d, uint32_t len) {   // m muss gehalten werden
        if (!inW) return false;
        BYTE hdr[5];
        hdr[0] = type;
        memcpy(hdr + 1, &len, 4);
        DWORD w = 0;
        if (!WriteFile(inW, hdr, 5, &w, nullptr) || w != 5) return false;
        if (len && (!WriteFile(inW, d, len, &w, nullptr) || w != len)) return false;
        return true;
    }
    void closeLocked() {
        running = false; ready = false; outstanding = 0;
        if (inW) { CloseHandle(inW); inW = nullptr; }
        if (proc) { TerminateProcess(proc, 0); CloseHandle(proc); proc = nullptr; }
        // outR schliesst der Lese-Thread
    }
    bool start(const std::string& cmdUtf8);
    bool sendAudio(const float* d, size_t n) {
        if (!ready) return false;
        if (outstanding.load() > 30) { skipped++; return false; }    // Worker haengt -> ohne Effekt weiter
        std::lock_guard<std::mutex> lk(m);
        if (!writeMsg(1, d, (uint32_t)(n * sizeof(float)))) { closeLocked(); return false; }
        outstanding++;
        return true;
    }
    void set(const std::string& text) {
        std::lock_guard<std::mutex> lk(m);
        lastSet = text;
        if (running && !writeMsg(2, text.data(), (uint32_t)text.size())) closeLocked();
    }
};
static FxWorker g_fx;

static DWORD WINAPI fxReader(LPVOID p) {
    HANDLE h = (HANDLE)p;
    std::vector<float> buf;
    for (;;) {
        uint32_t len = 0;
        if (!readExact(h, &len, 4)) break;
        if (len > 1 << 20) break;
        buf.resize(len / 4);
        if (len && !readExact(h, buf.data(), len)) break;
        if (len == 0) { g_fx.ready = true; continue; }
        if (g_fx.outstanding > 0) g_fx.outstanding--;
        if (g_voice.pymode == 2) pushVoice(buf.data(), buf.size());
    }
    CloseHandle(h);
    {
        std::lock_guard<std::mutex> lk(g_fx.m);
        if (g_fx.outR == h) { g_fx.outR = nullptr; g_fx.closeLocked(); }
    }
    return 0;
}

bool FxWorker::start(const std::string& cmdUtf8) {
    std::lock_guard<std::mutex> lk(m);
    if (running) return true;
    ULONGLONG now = GetTickCount64();
    if (lastStart && now - lastStart < 3000) return false;   // nicht im Kreis neu starten
    lastStart = now;
    SECURITY_ATTRIBUTES sa{sizeof(sa), nullptr, TRUE};
    HANDLE inR = nullptr, inW2 = nullptr, outR2 = nullptr, outW = nullptr;
    if (!CreatePipe(&inR, &inW2, &sa, 1 << 18)) return false;
    if (!CreatePipe(&outR2, &outW, &sa, 1 << 18)) { CloseHandle(inR); CloseHandle(inW2); return false; }
    SetHandleInformation(inW2, HANDLE_FLAG_INHERIT, 0);
    SetHandleInformation(outR2, HANDLE_FLAG_INHERIT, 0);
    HANDLE nul = CreateFileW(L"NUL", GENERIC_WRITE, FILE_SHARE_WRITE, &sa, OPEN_EXISTING, 0, nullptr);
    STARTUPINFOW si{};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES;
    si.hStdInput = inR;
    si.hStdOutput = outW;
    si.hStdError = nul;
    PROCESS_INFORMATION pi{};
    std::wstring cmd = widen(cmdUtf8.c_str());
    std::vector<wchar_t> cl(cmd.begin(), cmd.end());
    cl.push_back(0);
    BOOL ok = CreateProcessW(nullptr, cl.data(), nullptr, nullptr, TRUE,
                             CREATE_NO_WINDOW | CREATE_SUSPENDED | ABOVE_NORMAL_PRIORITY_CLASS,
                             nullptr, nullptr, &si, &pi);
    CloseHandle(inR); CloseHandle(outW);
    if (nul != INVALID_HANDLE_VALUE) CloseHandle(nul);
    if (!ok) { CloseHandle(inW2); CloseHandle(outR2); return false; }
    if (!job) {   // Worker stirbt automatisch mit dem Helfer
        job = CreateJobObjectW(nullptr, nullptr);
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION li{};
        li.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if (job) SetInformationJobObject(job, JobObjectExtendedLimitInformation, &li, sizeof(li));
    }
    if (job) AssignProcessToJobObject(job, pi.hProcess);
    ResumeThread(pi.hThread);
    CloseHandle(pi.hThread);
    proc = pi.hProcess;
    inW = inW2;
    outR = outR2;
    running = true;
    ready = false;
    outstanding = 0;
    restarts++;
    if (!lastSet.empty()) writeMsg(2, lastSet.data(), (uint32_t)lastSet.size());
    HANDLE th = CreateThread(nullptr, 0, fxReader, outR2, 0, nullptr);
    if (th) { SetThreadPriority(th, THREAD_PRIORITY_ABOVE_NORMAL); CloseHandle(th); }
    return true;
}
static std::string g_fxCmd;

struct ServerStream : StreamIO {
    uint16_t id = 0;
    std::string mode, arg;
    std::atomic<bool> stop{false};
    HANDLE dataEvent = CreateEventW(nullptr, FALSE, FALSE, nullptr);
    std::mutex m;
    std::vector<float> pending;
    ~ServerStream() { CloseHandle(dataEvent); }

    void log(const std::string& msg) override { sendFrame(2, id, msg.data(), (uint32_t)msg.size()); }
    bool emit(const float* d, size_t n) override {
        // Stille nicht als Daten schicken (spart Megabytes pro Sekunde), nur "N Frames Stille"
        bool silent = true;
        for (size_t i = 0; i < n; i++) { if (d[i] != 0.0f) { silent = false; break; } }
        if (silent) {
            uint32_t frames = (uint32_t)(n / 2);
            return sendFrame(5, id, &frames, 4);
        }
        return sendFrame(1, id, d, (uint32_t)(n * sizeof(float)));
    }
    bool stopped() override { return stop || g_quit; }
    // Wiedergabe: NICHT auf Python warten. Python fuellt einen Vorrat (~100 ms) auf; der Audio-Takt
    // laeuft unabhaengig weiter. Die native Stimme wird direkt dazugemischt.
    std::vector<float> py;          // Vorrat von Python (Stereo, interleaved)
    size_t pyR = 0;
    bool outstanding = false;
    ULONGLONG reqTime = 0;
    unsigned pyShort = 0;

    virtual void addData(const float* d, size_t nfloats) {
        std::lock_guard<std::mutex> lk(m);
        if (pyR > 0 && pyR >= py.size() / 2) {   // gelesenen Teil wegwerfen
            py.erase(py.begin(), py.begin() + pyR);
            pyR = 0;
        }
        py.insert(py.end(), d, d + nfloats);
        outstanding = false;
    }

    bool request(uint32_t frames, float* out) override {
        size_t need = (size_t)frames * 2;
        size_t level;
        {
            std::lock_guard<std::mutex> lk(m);
            size_t have = py.size() - pyR;
            size_t got = (std::min)(have, need);
            if (got) memcpy(out, py.data() + pyR, got * sizeof(float));
            if (got < need) { memset(out + got, 0, (need - got) * sizeof(float)); if (have || outstanding) pyShort++; }
            pyR += got;
            level = (py.size() - pyR) / 2;
            ULONGLONG now = GetTickCount64();
            if (outstanding && now - reqTime > 300) outstanding = false;     // Antwort verloren -> neu fragen
            if (!outstanding && level < 5760) {                               // < 120 ms Vorrat -> auf 160 ms auffuellen
                uint32_t ask = (uint32_t)(7680 - level);
                outstanding = true;
                reqTime = now;
                if (!sendFrame(3, id, &ask, 4)) return false;
            }
        }
        bool toCable = g_voice.enabled && g_voice.target.load() == (int)id;
        bool toMon = g_voice.monitor && g_voice.monTarget.load() == (int)id;
        if (toCable || toMon) {
            static thread_local double lastReq = 0;
            if (toCable) noteGap(g_renderGapMax, lastReq);
            static thread_local std::vector<float> v;
            v.resize(frames);
            (toCable ? g_voiceRing : g_monRing).read(v.data(), frames);
            float g = toCable ? g_voice.gain.load() : g_voice.monGain.load();
            for (uint32_t i = 0; i < frames; i++) {
                float x = v[i] * g;
                float a = out[2 * i] + x, b = out[2 * i + 1] + x;
                out[2 * i] = a > 1.f ? 1.f : (a < -1.f ? -1.f : a);
                out[2 * i + 1] = b > 1.f ? 1.f : (b < -1.f ? -1.f : b);
            }
        }
        return !stopped();
    }
};

// Mikrofon -> Filter -> RNNoise -> Gate -> Ring (laeuft komplett nativ)
struct VoiceInStream : ServerStream {
    void* rn = nullptr;
    std::vector<float> inbuf;
    float z1 = 0, z2 = 0;            // Biquad-Zustand (Hochpass 85 Hz)
    float b0, b1, b2, a1, a2;
    float gateGain = 1.f;
    int hold = 0;
    float peakIn = 0, peakOut = 0;
    int frameCount = 0;
    double lastEmit = 0;
    VoiceInStream() {
        const double PI = 3.14159265358979;
        double w0 = 2 * PI * 85.0 / OUT_RATE, cs = cos(w0), alpha = sin(w0) / (2 * 0.7071);
        double a0 = 1 + alpha;
        b0 = (float)(((1 + cs) / 2) / a0); b1 = (float)(-(1 + cs) / a0); b2 = b0;
        a1 = (float)((-2 * cs) / a0); a2 = (float)((1 - alpha) / a0);
        if (loadRnnoise()) rn = rn_create(nullptr);
    }
    ~VoiceInStream() { if (rn) rn_destroy(rn); }

    bool emit(const float* d, size_t nfl) override {
        size_t frames = nfl / 2;
        noteGap(g_micGapMax, lastEmit);
        for (size_t i = 0; i < frames; i++) {
            float x = 0.5f * (d[2 * i] + d[2 * i + 1]);
            float ax = fabsf(x);
            if (ax > peakIn) peakIn = ax;
            float y = b0 * x + z1;           // Transposed Direct Form II
            z1 = b1 * x - a1 * y + z2;
            z2 = b2 * x - a2 * y;
            inbuf.push_back(y);
        }
        float fr[480], outf[480];
        size_t pos = 0;
        while (inbuf.size() - pos >= 480) {
            for (int i = 0; i < 480; i++) fr[i] = inbuf[pos + i];
            pos += 480;
            float prob = 1.f;
            if (rn && g_voice.clean) {
                float tmp[480];
                for (int i = 0; i < 480; i++) tmp[i] = fr[i] * 32768.f;
                prob = rn_process(rn, outf, tmp);
                float st = g_voice.strength;
                for (int i = 0; i < 480; i++) outf[i] = (outf[i] / 32768.f) * st + fr[i] * (1.f - st);
            } else {
                memcpy(outf, fr, sizeof(fr));
            }
            if (rn && g_voice.clean && g_voice.gate) {
                if (prob > 0.30f) hold = 45; else if (hold > 0) hold--;
                float target = (prob > 0.30f || hold > 0) ? 1.f : 0.18f;
                float start = gateGain;
                float end = target > start ? target : start + (target - start) * 0.08f;
                for (int i = 0; i < 480; i++) outf[i] *= start + (end - start) * (float)i / 480.f;
                gateGain = end;
            }
            for (int i = 0; i < 480; i++) { float a = fabsf(outf[i]); if (a > peakOut) peakOut = a; }
            bool viaFx = false;
            if (g_voice.pymode == 2) {
                if (!g_fx.running && !g_fxCmd.empty()) g_fx.start(g_fxCmd);   // abgestuerzt -> neu starten
                viaFx = g_fx.sendAudio(outf, 480);
            }
            if (!viaFx) pushVoice(outf, 480);   // direkt (oder Effekt-Prozess noch nicht bereit)
            if (++frameCount >= 10) {        // alle 100 ms Pegel an Python melden
                float lv[2] = {peakIn, peakOut * g_voice.gain};
                sendFrame(6, id, lv, 8);
                peakIn = peakOut = 0;
                frameCount = 0;
            }
        }
        if (pos) inbuf.erase(inbuf.begin(), inbuf.begin() + pos);
        return !stopped();
    }
};

static std::mutex g_streamsLock;
static std::map<uint16_t, ServerStream*> g_streams;

static DWORD WINAPI streamThread(LPVOID p) {
    ServerStream* st = (ServerStream*)p;
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    int rc;
    if (st->mode == "play") rc = runPlay(st->arg.c_str(), *st);
    else if (st->mode == "voicein") {
        g_voiceRing.clear();
        if (st->arg.rfind("pid:", 0) == 0) rc = runCapture("process", st->arg.c_str() + 4, *st);   // fuer Tests
        else rc = runCapture("mic", st->arg.c_str(), *st);
    }
    else rc = runCapture(st->mode.c_str(), st->arg.c_str(), *st);
    int32_t code = rc;
    sendFrame(4, st->id, &code, 4);
    {
        std::lock_guard<std::mutex> lk(g_streamsLock);
        auto it = g_streams.find(st->id);
        if (it != g_streams.end() && it->second == st) g_streams.erase(it);
    }
    CoUninitialize();
    delete st;
    return 0;
}

// ---------------------------------------------------------------- Ducking: andere Apps leiser, solange ein Sound laeuft
// Merkt sich die Original-Lautstaerke jeder App (stabile Session-Kennung = App + Geraet, gilt auch ueber
// Neustarts der App hinweg) und stellt sie danach wieder her. Wurde eine App beendet, waehrend sie leiser war,
// wartet der Eintrag, bis die App wieder Ton macht, und setzt sie dann zurueck - sonst wuerde Windows sich die
// leise Lautstaerke fuer diese App dauerhaft merken. Die Werte stehen auch in %TEMP%\potato_clips_duck.txt
// (Absturz/Neustart des PCs).
static std::mutex g_duckLock;
static std::map<std::wstring, float> g_ducked;      // Session -> Original-Lautstaerke (solange wir sie veraendern)
static bool g_duckActive = false;
static float g_duckFac = 1.f;
static std::string g_duckSkip;                       // ",a.exe,b.exe," ; mit g_duckOnly = nur diese
static bool g_duckOnly = false;
static std::map<std::string, float> g_guard;         // Ohrenschutz: exe -> Faktor (< 1 = gerade leiser)

static std::wstring duckFile() {
    wchar_t t[MAX_PATH];
    GetTempPathW(MAX_PATH, t);
    return std::wstring(t) + L"potato_clips_duck.txt";
}

static std::string exeOf(DWORD pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return "";
    wchar_t buf[MAX_PATH];
    DWORD n = MAX_PATH;
    std::string out;
    if (QueryFullProcessImageNameW(h, 0, buf, &n)) {
        std::wstring w(buf, n);
        size_t k = w.find_last_of(L"\\/");
        out = utf8((k == std::wstring::npos ? w : w.substr(k + 1)).c_str());
        for (auto& c : out) c = (char)tolower((unsigned char)c);
    }
    CloseHandle(h);
    return out;
}

// fn(sessionId, volumeInterface, pid) fuer jede App-Session auf allen aktiven Ausgabegeraeten
template <class F>
static void forEachSession(F fn) {
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL, __uuidof(IMMDeviceEnumerator),
                                (void**)&en))) return;
    IMMDeviceCollection* col = nullptr;
    if (SUCCEEDED(en->EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE, &col))) {
        UINT cnt = 0;
        col->GetCount(&cnt);
        for (UINT i = 0; i < cnt; i++) {
            IMMDevice* dev = nullptr;
            if (FAILED(col->Item(i, &dev))) continue;
            IAudioSessionManager2* mgr = nullptr;
            if (SUCCEEDED(dev->Activate(__uuidof(IAudioSessionManager2), CLSCTX_ALL, nullptr, (void**)&mgr))) {
                IAudioSessionEnumerator* se = nullptr;
                if (SUCCEEDED(mgr->GetSessionEnumerator(&se))) {
                    int n = 0;
                    se->GetCount(&n);
                    for (int j = 0; j < n; j++) {
                        IAudioSessionControl* c = nullptr;
                        if (FAILED(se->GetSession(j, &c))) continue;
                        IAudioSessionControl2* c2 = nullptr;
                        if (SUCCEEDED(c->QueryInterface(__uuidof(IAudioSessionControl2), (void**)&c2))) {
                            DWORD pid = 0;
                            c2->GetProcessId(&pid);
                            LPWSTR sid = nullptr;
                            bool sys = c2->IsSystemSoundsSession() == S_OK;
                            if (!sys && pid && SUCCEEDED(c2->GetSessionIdentifier(&sid)) && sid) {
                                ISimpleAudioVolume* v = nullptr;
                                if (SUCCEEDED(c->QueryInterface(__uuidof(ISimpleAudioVolume), (void**)&v))) {
                                    fn(std::wstring(sid), v, pid);
                                    v->Release();
                                }
                            }
                            if (sid) CoTaskMemFree(sid);
                            c2->Release();
                        }
                        c->Release();
                    }
                    se->Release();
                }
                mgr->Release();
            }
            dev->Release();
        }
        col->Release();
    }
    en->Release();
}

static void saveDuckFile() {
    std::wstring f = duckFile();
    if (g_ducked.empty()) { DeleteFileW(f.c_str()); return; }
    FILE* fp = nullptr;
    if (_wfopen_s(&fp, f.c_str(), L"w, ccs=UTF-8") != 0 || !fp) return;
    for (auto& kv : g_ducked) fwprintf(fp, L"%.4f\t%s\n", kv.second, kv.first.c_str());
    fclose(fp);
}

// Wunsch-Lautstaerke jeder App = Original x Ducking x Ohrenschutz. Apps, die gerade nicht laufen, bleiben
// vorgemerkt und werden zurueckgesetzt, sobald sie wieder Ton machen (siehe duckWatch).
static void volApplyLocked() {
    DWORD me = GetCurrentProcessId();
    std::set<std::wstring> done;
    forEachSession([&](const std::wstring& sid, ISimpleAudioVolume* v, DWORD pid) {
        if (pid == me) return;
        std::string exe = exeOf(pid);
        if (exe.empty()) return;
        float f = 1.f;
        if (g_duckActive) {
            bool listed = g_duckSkip.find("," + exe + ",") != std::string::npos;
            if (g_duckOnly ? listed : !listed) f *= g_duckFac;
        }
        auto g = g_guard.find(exe);
        if (g != g_guard.end()) f *= g->second;
        auto it = g_ducked.find(sid);
        if (f < 0.999f) {
            float orig;
            if (it == g_ducked.end()) {
                if (FAILED(v->GetMasterVolume(&orig))) return;
                g_ducked[sid] = orig;
            } else {
                orig = it->second;
            }
            v->SetMasterVolume(orig * f, nullptr);
        } else if (it != g_ducked.end()) {
            v->SetMasterVolume(it->second, nullptr);
            done.insert(sid);
        }
    });
    for (auto& d : done) g_ducked.erase(d);
    saveDuckFile();
}

static void duckApply(float factor, const std::string& skipCsv) {
    std::lock_guard<std::mutex> lk(g_duckLock);
    g_duckActive = true;
    g_duckFac = factor;
    g_duckOnly = !skipCsv.empty() && skipCsv[0] == '+';          // "+a.exe,b.exe" = nur diese (fuer Tests)
    g_duckSkip = "," + (g_duckOnly ? skipCsv.substr(1) : skipCsv) + ",";
    volApplyLocked();
}

static void duckRestore() {
    std::lock_guard<std::mutex> lk(g_duckLock);
    g_duckActive = false;
    volApplyLocked();
}

static void guardSet(const std::string& exe, float factor) {
    std::lock_guard<std::mutex> lk(g_duckLock);
    if (factor >= 0.999f) g_guard.erase(exe);
    else g_guard[exe] = factor < 0.05f ? 0.05f : factor;
    volApplyLocked();
}

static void guardClear() {
    std::lock_guard<std::mutex> lk(g_duckLock);
    g_guard.clear();
    volApplyLocked();
}

// Alle 3 s: vorgemerkte Apps, die inzwischen wieder laufen, auf ihre alte Lautstaerke setzen
static void duckWatch() {
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    while (!g_quit) {
        for (int i = 0; i < 30 && !g_quit; i++) Sleep(100);
        std::lock_guard<std::mutex> lk(g_duckLock);
        if (!g_ducked.empty()) volApplyLocked();
    }
    CoUninitialize();
}

static void duckRecoverFromFile() {
    std::wstring f = duckFile();
    FILE* fp = nullptr;
    if (_wfopen_s(&fp, f.c_str(), L"r, ccs=UTF-8") != 0 || !fp) return;
    wchar_t line[2048];
    {
        std::lock_guard<std::mutex> lk(g_duckLock);
        while (fgetws(line, 2048, fp)) {
            wchar_t* tab = wcschr(line, L'\t');
            if (!tab) continue;
            *tab = 0;
            std::wstring id(tab + 1);
            while (!id.empty() && (id.back() == L'\n' || id.back() == L'\r')) id.pop_back();
            // aeltere Versionen speicherten die Kennung der laufenden Instanz ("...|1%b<pid>") - auf App kuerzen
            size_t bar = id.rfind(L"|1%b");
            if (bar != std::wstring::npos && std::count(id.begin(), id.end(), L'|') >= 2) id = id.substr(0, bar);
            if (!g_ducked.count(id)) g_ducked[id] = (float)_wtof(line);
        }
    }
    fclose(fp);
    duckRestore();
    DeleteFileW(f.c_str());
}

static int cmdServer() {
    HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
    sendFrame(2, 0, "audiocap: server ok", 19);
    duckRecoverFromFile();
    std::thread duckWatcher(duckWatch);
    duckWatcher.detach();
    std::vector<BYTE> buf;
    while (!g_quit) {
        BYTE hdr[7];
        if (!readExact(in, hdr, 7)) break;
        uint8_t type = hdr[0];
        uint16_t id;
        uint32_t len;
        memcpy(&id, hdr + 1, 2);
        memcpy(&len, hdr + 3, 4);
        if (len > 64 * 1024 * 1024) break;
        buf.resize(len);
        if (len && !readExact(in, buf.data(), len)) break;
        if (type == 1) {
            std::string cmd(buf.begin(), buf.end());
            if (cmd.rfind("start ", 0) == 0) {
                std::string rest = cmd.substr(6);
                size_t sp = rest.find(' ');
                std::string mode0 = rest.substr(0, rest.find(' '));
                ServerStream* st = mode0 == "voicein" ? new VoiceInStream() : new ServerStream();
                st->id = id;
                st->mode = rest.substr(0, sp);
                st->arg = sp == std::string::npos ? "" : rest.substr(sp + 1);
                {
                    std::lock_guard<std::mutex> lk(g_streamsLock);
                    auto it = g_streams.find(id);
                    if (it != g_streams.end()) it->second->stop = true;
                    g_streams[id] = st;
                }
                HANDLE th = CreateThread(nullptr, 0, streamThread, st, 0, nullptr);
                if (th) CloseHandle(th);
            } else if (cmd.rfind("voiceconf ", 0) == 0) {
                int en = 0, cl = 1, ga = 1, pm = 0, mo = 0;
                float stg = 0.85f, gn = 1.0f, mg = 0.8f;
                sscanf_s(cmd.c_str() + 10, "%d %d %d %f %f %d %d %f", &en, &cl, &ga, &stg, &gn, &pm, &mo, &mg);
                if (pm != 2) pm = 0;
                if (pm != g_voice.pymode.load()) {
                    // mit Effekt-Prozess: etwas mehr Puffer (Ziel 60 ms statt 40 ms)
                    if (pm == 2) { g_voiceRing.setParams(12000, 2880, 2400); g_monRing.setParams(12000, 2880, 2400); }
                    else { g_voiceRing.setParams(7200, 1920, 1440); g_monRing.setParams(7200, 1920, 1440); }
                    g_voice.pymode = pm;
                }
                if (!mo && g_voice.monitor) g_monRing.clear();
                g_voice.monitor = mo != 0;
                g_voice.monGain = mg;
                if (!en && g_voice.enabled) g_voiceRing.clear();
                g_voice.enabled = en != 0;
                g_voice.clean = cl != 0;
                g_voice.gate = ga != 0;
                g_voice.strength = stg;
                g_voice.gain = gn;
            } else if (cmd == "voicetarget") {
                g_voice.target = (int)id;
            } else if (cmd.rfind("duck ", 0) == 0) {
                float fac = 0.3f;
                char skip[1024] = {0};
                sscanf_s(cmd.c_str() + 5, "%f %1023s", &fac, skip, (unsigned)sizeof(skip));
                if (fac < 0.f) fac = 0.f;
                if (fac > 1.f) fac = 1.f;
                duckApply(fac, skip);
            } else if (cmd == "unduck") {
                duckRestore();
            } else if (cmd.rfind("guard ", 0) == 0) {
                char exe[512] = {0};
                float fac = 1.f;
                if (sscanf_s(cmd.c_str() + 6, "%511s %f", exe, (unsigned)sizeof(exe), &fac) == 2) {
                    std::string e(exe);
                    for (auto& c : e) c = (char)tolower((unsigned char)c);
                    if (fac < 0.f) fac = 0.f;
                    guardSet(e, fac);
                }
            } else if (cmd == "unguard") {
                guardClear();
            } else if (cmd == "montarget") {
                g_voice.monTarget = (int)id;
            } else if (cmd.rfind("fxstart ", 0) == 0) {
                g_fxCmd = cmd.substr(8);
                g_fx.start(g_fxCmd);
            } else if (cmd.rfind("fxset ", 0) == 0) {
                g_fx.set(cmd.substr(6));
            } else if (cmd == "stats") {
                char b[400];
                double fillMs = 0, ppm = 0;
                g_voiceRing.info(fillMs, ppm);
                unsigned pyShort = 0;
                {
                    std::lock_guard<std::mutex> lk(g_streamsLock);
                    for (auto& kv : g_streams) pyShort += kv.second->pyShort;
                }
                sprintf_s(b, "stats voice_underruns=%u voice_drops=%u py_short=%u rnnoise=%d render_gap=%u mic_gap=%u out_dropped=%u fill_ms=%d drift_ppm=%d pymode=%d fx_ready=%d fx_starts=%u fx_skipped=%u",
                          g_voiceRing.underruns, g_voiceRing.drops, pyShort, loadRnnoise() ? 1 : 0,
                          g_renderGapMax.exchange(0), g_micGapMax.exchange(0), g_outDropped.load(),
                          (int)fillMs, (int)ppm, g_voice.pymode.load(), g_fx.ready ? 1 : 0,
                          g_fx.restarts.load(), g_fx.skipped.load());
                sendFrame(2, 0, b, (uint32_t)strlen(b));
            } else if (cmd == "stop") {
                std::lock_guard<std::mutex> lk(g_streamsLock);
                auto it = g_streams.find(id);
                if (it != g_streams.end()) it->second->stop = true;
            }
        } else if (type == 2) {
            std::lock_guard<std::mutex> lk(g_streamsLock);
            auto it = g_streams.find(id);
            if (it != g_streams.end()) {
                it->second->addData((const float*)buf.data(), len / 4);
            }
        }
    }
    // stdin zu -> alles beenden
    g_quit = true;
    {
        std::lock_guard<std::mutex> lk(g_streamsLock);
        for (auto& kv : g_streams) kv.second->stop = true;
    }
    {
        std::lock_guard<std::mutex> lk(g_duckLock);
        g_guard.clear();
    }
    duckRestore();
    Sleep(300);
    flushOut(500);
    return 0;
}

static int cmdSetVolume(const char* idArg, const char* volArg) {
    IMMDeviceEnumerator* en = nullptr;
    if (FAILED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr, CLSCTX_ALL,
                                __uuidof(IMMDeviceEnumerator), (void**)&en))) return 2;
    IMMDevice* d = nullptr;
    HRESULT hr = en->GetDevice(widen(idArg).c_str(), &d);
    en->Release();
    if (FAILED(hr) || !d) { logerr("Geraet nicht gefunden", hr); return 4; }
    IAudioEndpointVolume* ev = nullptr;
    hr = d->Activate(__uuidof(IAudioEndpointVolume), CLSCTX_ALL, nullptr, (void**)&ev);
    d->Release();
    if (FAILED(hr)) { logerr("EndpointVolume", hr); return 4; }
    float v = (float)atof(volArg);
    if (v < 0) v = 0;
    if (v > 1) v = 1;
    ev->SetMasterVolumeLevelScalar(v, nullptr);
    ev->SetMute(FALSE, nullptr);
    ev->Release();
    return 0;
}

// Diagnose: alle App-Lautstaerken anzeigen bzw. eine App auf eine Lautstaerke setzen
static int cmdSessions(const char* exeArg, const char* volArg) {
    std::string want = exeArg ? exeArg : "";
    for (auto& c : want) c = (char)tolower((unsigned char)c);
    float nv = volArg ? (float)atof(volArg) : -1.f;
    forEachSession([&](const std::wstring& sid, ISimpleAudioVolume* v, DWORD pid) {
        std::string exe = exeOf(pid);
        if (!want.empty() && exe != want) return;
        if (nv >= 0.f && nv <= 1.f) v->SetMasterVolume(nv, nullptr);
        float cur = 0.f;
        v->GetMasterVolume(&cur);
        printf("%s\t%.3f\t%lu\n", exe.c_str(), cur, (unsigned long)pid);
    });
    return 0;
}

int main(int argc, char** argv) {
    timeBeginPeriod(1);   // Windows-Timer auf 1 ms (Standard 15,6 ms -> Audio kaeme sonst in Schueben)
    _setmode(_fileno(stdout), _O_BINARY);
    _setmode(_fileno(stdin), _O_BINARY);
    if (FAILED(CoInitializeEx(nullptr, COINIT_MULTITHREADED))) return 1;
    int rc = 1;
    if (argc >= 2 && strcmp(argv[1], "list") == 0) rc = cmdList();
    else if (argc >= 2 && strcmp(argv[1], "server") == 0) rc = cmdServer();
    else if (argc >= 3 && strcmp(argv[1], "play") == 0) rc = cmdPlay(argv[2]);
    else if (argc >= 4 && strcmp(argv[1], "setvolume") == 0) rc = cmdSetVolume(argv[2], argv[3]);
    else if (argc >= 2 && strcmp(argv[1], "sessions") == 0)
        rc = cmdSessions(argc >= 3 ? argv[2] : nullptr, argc >= 4 ? argv[3] : nullptr);
    else if (argc >= 3 && (strcmp(argv[1], "process") == 0 || strcmp(argv[1], "loopback") == 0 ||
                           strcmp(argv[1], "mic") == 0)) rc = cmdCapture(argv[1], argv[2]);
    else fprintf(stderr, "usage: audiocap list | server | play <id|default> | process <pid> | loopback <id|default> | mic <id|default>\n");
    CoUninitialize();
    timeEndPeriod(1);
    return rc;
}
