#include "ble_uart.h"

#include <Arduino.h>
#include <BLE2902.h>
#include <BLECharacteristic.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <string.h>

#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>

#define BLE_UART_SERVICE_UUID "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_UART_RX_UUID "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_UART_TX_UUID "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"
#define BLE_UART_QUEUE_LEN 4
#define BLE_UART_READVERTISE_MS 500

static QueueHandle_t s_lines = NULL;
static BLEServer *s_server = NULL;
static BLECharacteristic *s_tx = NULL;
static bool s_connected = false;
static bool s_subscribed = false;
static unsigned long s_readvertise_at = 0;

static char s_accum[BLE_UART_MAX_LINE + 1];
static size_t s_accum_len = 0;
static bool s_accum_overflow = false;

class BleUartRxCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *characteristic) override
    {
        uint8_t * data = characteristic->getData();
        size_t len = characteristic->getLength();
        for(size_t i = 0; i < len; i++) {
            char ch = (char)data[i];
            if(ch == '\r') {
                continue;
            }
            if(ch == '\n') {
                if(s_accum_overflow) {
                    char marker[BLE_UART_MAX_LINE + 1] = {0};
                    marker[0] = '\x01';
                    xQueueSend(s_lines, marker, 0);
                }
                else if(s_accum_len > 0) {
                    char line[BLE_UART_MAX_LINE + 1];
                    memcpy(line, s_accum, s_accum_len);
                    line[s_accum_len] = '\0';
                    xQueueSend(s_lines, line, 0);
                }
                s_accum_len = 0;
                s_accum_overflow = false;
                continue;
            }
            if(s_accum_overflow) {
                continue;
            }
            if(s_accum_len < BLE_UART_MAX_LINE) {
                s_accum[s_accum_len++] = ch;
            }
            else {
                s_accum_len = 0;
                s_accum_overflow = true;
            }
        }
    }
};

class BleUartTxCallbacks : public BLECharacteristicCallbacks {
    void onSubscribe(BLECharacteristic * characteristic,
                     ble_gap_conn_desc * desc,
                     uint16_t subValue) override
    {
        (void)characteristic;
        (void)desc;
        s_subscribed = subValue != 0;
    }
};

class BleUartServerCallbacks : public BLEServerCallbacks {
    void onConnect(BLEServer * server) override
    {
        (void)server;
        s_connected = true;
        s_readvertise_at = 0;
    }

    void onDisconnect(BLEServer * server) override
    {
        (void)server;
        s_connected = false;
        s_subscribed = false;
        s_readvertise_at = millis() + BLE_UART_READVERTISE_MS;
    }
};

void ble_uart_begin(const char * name)
{
    s_lines = xQueueCreate(BLE_UART_QUEUE_LEN, BLE_UART_MAX_LINE + 1);
    if(s_lines == NULL) {
        Serial.println("[ble] queue allocation failed");
        return;
    }

    BLEDevice::init(name);
    BLEDevice::setMTU(256);
    s_server = BLEDevice::createServer();
    s_server->setCallbacks(new BleUartServerCallbacks());

    BLEService * service = s_server->createService(BLE_UART_SERVICE_UUID);
    s_tx = service->createCharacteristic(BLE_UART_TX_UUID,
                                         BLECharacteristic::PROPERTY_NOTIFY);
    s_tx->setCallbacks(new BleUartTxCallbacks());
    s_tx->addDescriptor(new BLE2902());

    BLECharacteristic * rx = service->createCharacteristic(
        BLE_UART_RX_UUID,
        BLECharacteristic::PROPERTY_WRITE |
            BLECharacteristic::PROPERTY_WRITE_NR);
    rx->setCallbacks(new BleUartRxCallbacks());

    service->start();

    BLEAdvertising * advertising = s_server->getAdvertising();
    advertising->addServiceUUID(BLE_UART_SERVICE_UUID);
    advertising->setName(name);
    advertising->setScanResponse(true);
    advertising->start();
    Serial.printf("[ble] advertising as %s, mtu=%u\n", name,
                  BLEDevice::getMTU());
}

bool ble_uart_pop_line(char * out, size_t cap)
{
    if(s_lines == NULL || out == NULL || cap == 0) {
        return false;
    }
    char line[BLE_UART_MAX_LINE + 1];
    if(xQueueReceive(s_lines, line, 0) != pdTRUE) {
        return false;
    }
    size_t len = strlen(line);
    if(len >= cap) {
        len = cap - 1;
    }
    memcpy(out, line, len);
    out[len] = '\0';
    return true;
}

void ble_uart_send(const char * data, size_t len)
{
    if(!s_connected || !s_subscribed || s_server == NULL || s_tx == NULL) {
        return;
    }
    uint16_t mtu = s_server->getPeerMTU(s_server->getConnId());
    if(mtu < 23) {
        mtu = 23;
    }
    size_t chunk = (size_t)mtu - 3;
    if(chunk > 253) {
        chunk = 253;
    }
    if(chunk < 20) {
        chunk = 20;
    }
    for(size_t offset = 0; offset < len; offset += chunk) {
        size_t n = len - offset;
        if(n > chunk) {
            n = chunk;
        }
        s_tx->setValue((uint8_t *)(data + offset), n);
        s_tx->notify();
        delay(1);
    }
}

void ble_uart_send_line(const char * text)
{
    ble_uart_send(text, strlen(text));
    ble_uart_send("\n", 1);
}

bool ble_uart_connected(void)
{
    return s_connected && s_subscribed;
}

uint16_t ble_uart_mtu(void)
{
    return BLEDevice::getMTU();
}

void ble_uart_poll(void)
{
    if(s_readvertise_at == 0 || s_connected || s_server == NULL) {
        return;
    }
    if((long)(millis() - s_readvertise_at) >= 0) {
        s_readvertise_at = 0;
        s_server->startAdvertising();
        Serial.println("[ble] advertising again");
    }
}
