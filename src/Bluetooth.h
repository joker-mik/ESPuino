#pragma once

#include <Arduino.h>

#include <vector>

#ifdef BLUETOOTH_ENABLE
	#include "esp_bt_defs.h"
	#include "esp_gap_bt_api.h"

struct ScannedBluetoothDevice {
	char name[ESP_BT_GAP_MAX_BDNAME_LEN + 1];
	esp_bd_addr_t address;
	int rssi;
};
#endif

void Bluetooth_Init(void);
void Bluetooth_Exit(void);
void Bluetooth_Cyclic(void);

// AVRC commands, see https://github.com/pschatzmann/ESP32-A2DP/wiki/Controlling-your-Phone-with-AVRC-Commands

// Support for AVRC Commands starting from ESP32 Release 1.0.6
void Bluetooth_PlayPauseTrack(void);
void Bluetooth_NextTrack(void);
void Bluetooth_PreviousTrack(void);

// Support for AVRC Commands starting from ESP32 Release 2.0.0
void Bluetooth_SetVolume(const int32_t _newVolume);
uint8_t Bluetooth_GetCurrentVolume();

struct BluetoothSourceBufferStats {
	bool allocated;
	size_t capacity;
	size_t bytesWaiting;
	uint32_t minBytesWaiting;
	uint32_t maxBytesWaiting;
	uint32_t averageBytesWaiting;
	uint32_t underruns;
	uint32_t sendFailures;
	uint32_t bytesWritten;
	uint32_t bytesRead;
	uint32_t producerBytesPerSecond;
	uint32_t consumerBytesPerSecond;
	uint32_t lastProducerMsAgo;
	uint32_t lastConsumerMsAgo;
};

bool Bluetooth_Source_SendAudioData(const int16_t *outBuff, int16_t validSamples);
void Bluetooth_Source_ResetDiagnostics();
BluetoothSourceBufferStats Bluetooth_GetSourceBufferStats();
bool Bluetooth_Device_Connected();

#ifdef BLUETOOTH_ENABLE
void Bluetooth_StartScan();
void Bluetooth_ConnectToAddress(esp_bd_addr_t address);
std::vector<ScannedBluetoothDevice> Bluetooth_GetScannedDevices();
bool Bluetooth_GetConnectedSourceInfo(String &name, String &address);
#endif
